#!/usr/bin/env python3
"""
setup_keycloak_realm.py

Configura (o repara) un realm de Keycloak para un escenario MCP con dos
clientes: uno publico (para login) y uno confidencial (que expone roles
de cliente que necesitamos ver reflejados en el access token).

Qué hace:
  1. Obtiene un token de admin contra el realm 'master'.
  2. Crea (si no existe) el client scope 'roles' con mappers:
       - realm roles  -> realm_access.roles
       - client roles -> resource_access.<client_id>.roles
  3. Crea (si no existen) los dos clientes:
       - CLIENT_PUBLIC_ID   (publicClient=True)
       - CLIENT_CONFIDENTIAL_ID (publicClient=False, con secret)
  4. Asigna el scope 'roles' como default al cliente publico.
  5. Crea los client roles indicados en CONFIDENTIAL_ROLES sobre el
     cliente confidencial.
  6. (Opcional) Asigna esos roles a un usuario dado por USERNAME.

Es idempotente: se puede correr varias veces sin duplicar nada.

Uso:
    export KC_BASE_URL="https://mi-keycloak.example.com"
    export KC_REALM="prepaid-mcp-servers"
    export KC_ADMIN_USER="admin"
    export KC_ADMIN_PASSWORD="********"
    python3 setup_keycloak_realm.py
"""

import os
import sys
import json
import requests

# ---------------------------------------------------------------------------
# Configuración (via variables de entorno, con defaults razonables)
# ---------------------------------------------------------------------------

KC_BASE_URL = os.environ.get("KC_BASE_URL", "http://localhost:8081")
KC_REALM = os.environ.get("KC_REALM", "prepaid-mcp-servers")

# Credenciales de admin (realm master, cliente admin-cli por defecto)
KC_ADMIN_USER = os.environ.get("KC_ADMIN_USER", "admin")
KC_ADMIN_PASSWORD = os.environ.get("KC_ADMIN_PASSWORD", "admin")
KC_ADMIN_REALM = os.environ.get("KC_ADMIN_REALM", "master")
KC_ADMIN_CLIENT_ID = os.environ.get("KC_ADMIN_CLIENT_ID", "admin-cli")

CLIENT_PUBLIC_ID = os.environ.get("CLIENT_PUBLIC_ID", "mcp-remedy-client")
CLIENT_CONFIDENTIAL_ID = os.environ.get("CLIENT_CONFIDENTIAL_ID", "mcp-remedy-server")

# Client M2M opcional para agentes/automatizaciones headless (Client Credentials Grant,
# sin browser ni usuario humano). Dejar CLIENT_AGENT_ID vacio para saltear su creacion.
CLIENT_AGENT_ID = os.environ.get("CLIENT_AGENT_ID", "")

# Roles de cliente a crear sobre CLIENT_CONFIDENTIAL_ID
CONFIDENTIAL_ROLES = os.environ.get("CONFIDENTIAL_ROLES", "remedy-writer,remedy-reader").split(",")

# Roles (ya creados sobre CLIENT_CONFIDENTIAL_ID) a asignarle a la service account del
# client de agente. Subconjunto o igual a CONFIDENTIAL_ROLES.
AGENT_ROLES = os.environ.get("AGENT_ROLES", "remedy-writer,remedy-reader").split(",")

# Usuario al que asignarle los roles (opcional; dejar vacio para saltear)
USERNAME = os.environ.get("KC_TARGET_USERNAME", "cyazky")

# Roles a asignarle al usuario (subset o igual a CONFIDENTIAL_ROLES)
USER_ROLES = os.environ.get("KC_TARGET_USER_ROLES", "remedy-writer,remedy-reader").split(",")

TIMEOUT = 10


# ---------------------------------------------------------------------------
# Helpers HTTP
# ---------------------------------------------------------------------------

def get_admin_token() -> str:
    """Obtiene un access_token de admin usando password grant contra admin-cli."""
    url = f"{KC_BASE_URL}/realms/{KC_ADMIN_REALM}/protocol/openid-connect/token"
    data = {
        "grant_type": "password",
        "client_id": KC_ADMIN_CLIENT_ID,
        "username": KC_ADMIN_USER,
        "password": KC_ADMIN_PASSWORD,
    }
    resp = requests.post(url, data=data, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()["access_token"]


class KeycloakAdmin:
    def __init__(self, token: str):
        self.base = f"{KC_BASE_URL}/admin/realms/{KC_REALM}"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    # -- generic helpers ---------------------------------------------------

    def get(self, path: str, **kwargs):
        resp = requests.get(f"{self.base}{path}", headers=self.headers, timeout=TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp.json() if resp.text else None

    def post(self, path: str, payload: dict):
        resp = requests.post(f"{self.base}{path}", headers=self.headers, json=payload, timeout=TIMEOUT)
        if resp.status_code not in (201, 204):
            resp.raise_for_status()
        return resp

    def put(self, path: str, payload: dict):
        resp = requests.put(f"{self.base}{path}", headers=self.headers, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp

    # -- realm existence -----------------------------------------------------

    def ensure_realm_exists(self):
        url = f"{KC_BASE_URL}/admin/realms/{KC_REALM}"
        resp = requests.get(url, headers=self.headers, timeout=TIMEOUT)
        if resp.status_code == 404:
            print(f"[!] El realm '{KC_REALM}' no existe. Creándolo...")
            create_url = f"{KC_BASE_URL}/admin/realms"
            payload = {"realm": KC_REALM, "enabled": True}
            r = requests.post(create_url, headers=self.headers, json=payload, timeout=TIMEOUT)
            r.raise_for_status()
            print(f"[+] Realm '{KC_REALM}' creado.")
        else:
            resp.raise_for_status()
            print(f"[=] Realm '{KC_REALM}' ya existe.")

    # -- client scopes --------------------------------------------------------

    def find_client_scope_by_name(self, name: str):
        scopes = self.get("/client-scopes")
        for s in scopes:
            if s["name"] == name:
                return s
        return None

    def ensure_roles_scope(self) -> str:
        """Crea el client scope 'roles' con sus mappers si no existe. Devuelve su id."""
        existing = self.find_client_scope_by_name("roles")
        if existing:
            print("[=] Client scope 'roles' ya existe.")
            scope_id = existing["id"]
        else:
            print("[+] Creando client scope 'roles'...")
            payload = {
                "name": "roles",
                "description": "OpenID Connect scope for add user roles to the access token",
                "protocol": "openid-connect",
                "attributes": {
                    "include.in.token.scope": "true",
                    "display.on.consent.screen": "true",
                },
            }
            self.post("/client-scopes", payload)
            existing = self.find_client_scope_by_name("roles")
            scope_id = existing["id"]
            print(f"[+] Client scope 'roles' creado (id={scope_id}).")

        self._ensure_scope_mappers(scope_id)
        return scope_id

    def _ensure_scope_mappers(self, scope_id: str):
        mappers = self.get(f"/client-scopes/{scope_id}/protocol-mappers/models")
        mapper_names = {m["name"] for m in mappers}

        if "realm roles" not in mapper_names:
            print("    [+] Agregando mapper 'realm roles'...")
            self.post(f"/client-scopes/{scope_id}/protocol-mappers/models", {
                "name": "realm roles",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-realm-role-mapper",
                "config": {
                    "claim.name": "realm_access.roles",
                    "jsonType.label": "String",
                    "multivalued": "true",
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "true",
                },
            })
        else:
            print("    [=] Mapper 'realm roles' ya existe.")

        if "client roles" not in mapper_names:
            print("    [+] Agregando mapper 'client roles'...")
            self.post(f"/client-scopes/{scope_id}/protocol-mappers/models", {
                "name": "client roles",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-client-role-mapper",
                "config": {
                    "usermodel.clientRoleMapping.clientId": "",  # vacio = todos los clientes
                    "claim.name": "resource_access.${client_id}.roles",
                    "jsonType.label": "String",
                    "multivalued": "true",
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "userinfo.token.claim": "true",
                },
            })
        else:
            print("    [=] Mapper 'client roles' ya existe.")

    # -- clients ---------------------------------------------------------------

    def find_client_by_client_id(self, client_id: str):
        clients = self.get("/clients", params={"clientId": client_id})
        return clients[0] if clients else None

    def ensure_public_client(self, client_id: str) -> dict:
        existing = self.find_client_by_client_id(client_id)
        if existing:
            print(f"[=] Cliente publico '{client_id}' ya existe.")
            return existing

        print(f"[+] Creando cliente publico '{client_id}'...")
        payload = {
            "clientId": client_id,
            "publicClient": True,
            "protocol": "openid-connect",
            "standardFlowEnabled": True,
            "directAccessGrantsEnabled": True,
            "redirectUris": ["*"],  # ajustar a las URIs reales en produccion
            "webOrigins": ["*"],
            "enabled": True,
        }
        self.post("/clients", payload)
        return self.find_client_by_client_id(client_id)

    def ensure_confidential_client(self, client_id: str) -> dict:
        existing = self.find_client_by_client_id(client_id)
        if existing:
            print(f"[=] Cliente confidencial '{client_id}' ya existe.")
            return existing

        print(f"[+] Creando cliente confidencial '{client_id}'...")
        payload = {
            "clientId": client_id,
            "publicClient": False,
            "protocol": "openid-connect",
            "serviceAccountsEnabled": True,
            "standardFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "enabled": True,
        }
        self.post("/clients", payload)
        return self.find_client_by_client_id(client_id)

    def ensure_agent_client(self, client_id: str) -> dict:
        """
        Client M2M (Client Credentials Grant) para un agente headless — separado del
        client 'resource server' (CLIENT_CONFIDENTIAL_ID) a proposito, aunque ambos sean
        confidential+serviceAccountsEnabled: mezclar 'identidad del resource server' con
        'identidad de un consumidor M2M' impide revocar/rotar el acceso de un agente sin
        redeployar el server, y bloquea tener varios agentes con distintos roles.
        """
        existing = self.find_client_by_client_id(client_id)
        if existing:
            print(f"[=] Cliente de agente M2M '{client_id}' ya existe.")
            return existing

        print(f"[+] Creando cliente de agente M2M '{client_id}'...")
        payload = {
            "clientId": client_id,
            "publicClient": False,
            "protocol": "openid-connect",
            "serviceAccountsEnabled": True,
            "standardFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "enabled": True,
        }
        self.post("/clients", payload)
        return self.find_client_by_client_id(client_id)

    def ensure_audience_mapper(self, client_uuid: str, target_audience: str):
        """
        Agrega (si falta) un mapper 'Audience' hardcodeado en el scope DEDICADO del
        cliente dado — el mismo mecanismo que ya usa CLIENT_CONFIDENTIAL_ID para
        estampar su propio aud en los tokens que el emite via Client Credentials.
        El endpoint /protocol-mappers/models de un client es exactamente su scope
        dedicado (lo que la consola de Keycloak muestra como '{client}-dedicated').
        """
        mappers = self.get(f"/clients/{client_uuid}/protocol-mappers/models")
        if any(m["name"] == "audience-mapper" for m in mappers):
            print("    [=] Audience mapper ya existe.")
            return
        print(f"    [+] Agregando audience mapper (aud={target_audience})...")
        self.post(f"/clients/{client_uuid}/protocol-mappers/models", {
            "name": "audience-mapper",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            "config": {
                "included.client.audience": target_audience,
                "id.token.claim": "false",
                "access.token.claim": "true",
            },
        })

    def get_service_account_user_id(self, client_uuid: str) -> str:
        user = self.get(f"/clients/{client_uuid}/service-account-user")
        return user["id"]

    def get_client_secret(self, client_uuid: str) -> str:
        return self.get(f"/clients/{client_uuid}/client-secret")["value"]

    def assign_default_scope_to_client(self, client_uuid: str, scope_id: str, scope_name: str):
        # PUT es idempotente: si ya esta asignado, no rompe nada.
        url = f"/clients/{client_uuid}/default-client-scopes/{scope_id}"
        resp = requests.put(f"{self.base}{url}", headers=self.headers, timeout=TIMEOUT)
        if resp.status_code in (204, 201):
            print(f"[+] Scope '{scope_name}' asignado como default al cliente.")
        else:
            resp.raise_for_status()

    # -- client roles -------------------------------------------------------

    def ensure_client_role(self, client_uuid: str, role_name: str):
        existing = self.get(f"/clients/{client_uuid}/roles/{role_name}") if self._role_exists(client_uuid, role_name) else None
        if existing:
            print(f"    [=] Role de cliente '{role_name}' ya existe.")
            return existing
        print(f"    [+] Creando role de cliente '{role_name}'...")
        self.post(f"/clients/{client_uuid}/roles", {"name": role_name})
        return self.get(f"/clients/{client_uuid}/roles/{role_name}")

    def _role_exists(self, client_uuid: str, role_name: str) -> bool:
        try:
            self.get(f"/clients/{client_uuid}/roles/{role_name}")
            return True
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return False
            raise

    # -- users ---------------------------------------------------------------

    def find_user_by_username(self, username: str):
        users = self.get("/users", params={"username": username, "exact": "true"})
        return users[0] if users else None

    def assign_client_roles_to_user(self, user_id: str, client_uuid: str, roles: list):
        role_reps = []
        for r in roles:
            r = r.strip()
            if not r:
                continue
            role_reps.append(self.get(f"/clients/{client_uuid}/roles/{r}"))
        if not role_reps:
            return
        self.post(f"/users/{user_id}/role-mappings/clients/{client_uuid}", role_reps)
        print(f"[+] Roles {[r['name'] for r in role_reps]} asignados al usuario.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"== Configurando realm '{KC_REALM}' en {KC_BASE_URL} ==\n")

    try:
        token = get_admin_token()
    except requests.HTTPError as e:
        print(f"[x] No se pudo autenticar como admin: {e}", file=sys.stderr)
        sys.exit(1)

    kc = KeycloakAdmin(token)
    kc.ensure_realm_exists()

    # 1. Client scope 'roles' + mappers
    scope_id = kc.ensure_roles_scope()

    # 2. Clientes
    public_client = kc.ensure_public_client(CLIENT_PUBLIC_ID)
    confidential_client = kc.ensure_confidential_client(CLIENT_CONFIDENTIAL_ID)

    # 3. Asignar scope 'roles' como default al cliente publico (el que loguea)
    kc.assign_default_scope_to_client(public_client["id"], scope_id, "roles")

    # 4. Roles de cliente sobre el server confidencial
    print(f"\n[.] Creando roles en '{CLIENT_CONFIDENTIAL_ID}'...")
    for role_name in CONFIDENTIAL_ROLES:
        role_name = role_name.strip()
        if role_name:
            kc.ensure_client_role(confidential_client["id"], role_name)

    # 5. (Opcional) asignar roles a un usuario
    if USERNAME:
        print(f"\n[.] Asignando roles a usuario '{USERNAME}'...")
        user = kc.find_user_by_username(USERNAME)
        if not user:
            print(f"[x] Usuario '{USERNAME}' no encontrado, se salteo la asignacion.")
        else:
            kc.assign_client_roles_to_user(user["id"], confidential_client["id"], USER_ROLES)
    else:
        print("\n[.] KC_TARGET_USERNAME no seteado, se saltea asignacion de roles a usuario.")

    # 6. (Opcional) client M2M para un agente headless (Client Credentials Grant)
    if CLIENT_AGENT_ID:
        print(f"\n[.] Configurando cliente de agente M2M '{CLIENT_AGENT_ID}'...")
        agent_client = kc.ensure_agent_client(CLIENT_AGENT_ID)
        kc.assign_default_scope_to_client(agent_client["id"], scope_id, "roles")
        kc.ensure_audience_mapper(agent_client["id"], CLIENT_CONFIDENTIAL_ID)
        service_account_user_id = kc.get_service_account_user_id(agent_client["id"])
        kc.assign_client_roles_to_user(service_account_user_id, confidential_client["id"], AGENT_ROLES)
        agent_secret = kc.get_client_secret(agent_client["id"])
        print(f"[+] Client secret de '{CLIENT_AGENT_ID}' (guardalo en el .env del agente, no se vuelve a mostrar acá):")
        print(f"    {agent_secret}")
    else:
        print("\n[.] CLIENT_AGENT_ID no seteado, se saltea el cliente de agente M2M.")

    print("\n== Listo. Verificá con 'Evaluate' en el admin console o generando un token real. ==")


if __name__ == "__main__":
    main()

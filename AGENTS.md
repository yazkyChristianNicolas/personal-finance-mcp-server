# AGENTS.md

Operating instructions for anyone (human or AI) about to change this repo.
For run instructions aimed at a human skimming GitHub, see `README.md`.

## Purpose

MCP server remoto para `personal-finance-service` — expone sus operaciones
de negocio (groups, payment-methods, expenses) como tools MCP, autenticado
con Keycloak. Scaffoldeado con los skills `remote-mcp-keycloak` (template +
auth), `swagger-to-mcp-tools` (generación de tools desde el Swagger de
`personal-finance-service`) y `mcp-integration-tests` (tests de integración).

Atiende dos tipos de consumidores:
- **Humanos** (Kiro/Claude): login interactivo Authorization Code + PKCE.
- **Un agente headless** (`mcp-personal-finance-agent`): login M2M Client
  Credentials, sin browser ni usuario humano de por medio.

## Dependencia externa: personal-finance-service

Este repo **no** levanta Keycloak ni la API — se conecta a las que ya corren
en el `docker-compose.yml` de `personal-finance-service` (misma red Docker,
`personal-finance-service_default`, y mismo realm de Keycloak,
`personal-finance` — ver "Non-obvious decisions"). Levantar ese stack
primero:

```bash
cd ../personal-finance-service && docker compose up -d
```

## Running it locally

```bash
cp .env.example .env   # completar KEYCLOAK_CLIENT_SECRET (ver Keycloak setup abajo)
docker compose up -d --build
```

Faster iteration loop:

```bash
pip install -e ".[dev]"
uvicorn src.main:app --reload --port 8000
```

`GET /health`, `GET /.well-known/oauth-authorization-server` (sin auth).
`POST /mcp` requiere `Authorization: Bearer <jwt>` — un JWT humano
(Keycloak, mismo realm que `personal-finance-service`) o del agente M2M.

## Setup de Keycloak (clients de este MCP)

```bash
KC_BASE_URL=http://localhost:8080 KC_REALM=personal-finance \
CLIENT_PUBLIC_ID=mcp-personal-finance-client \
CLIENT_CONFIDENTIAL_ID=mcp-personal-finance-server \
CLIENT_AGENT_ID=mcp-personal-finance-agent \
CONFIDENTIAL_ROLES=finance-writer,finance-reader \
AGENT_ROLES=finance-writer,finance-reader \
KC_TARGET_USERNAME=testuser \
KC_ADMIN_USER=admin KC_ADMIN_PASSWORD=admin \
python3 tests/keycloak/script/setup_keycloak_realm.py
```

Reusa el realm `personal-finance` que ya trae `personal-finance-service`
(ver `keycloak/realm-export.json` en ese repo) — no crea un realm nuevo. El
script imprime el `client_secret` del agente una única vez al final; copiarlo
a `AGENT_CLIENT_SECRET` si vas a correr el agente headless.

## Probar con un custom connector remoto real (Claude Desktop / claude.ai)

Claude se conecta **desde la nube de Anthropic**, no desde tu máquina — ni
`localhost` ni una red privada sirven. Para probar en dev sin desplegar en
ningún lado:

1. Túnel público para el MCP: `cloudflared tunnel --url http://localhost:8000`
   → actualizar `SERVER_URL` en `.env` con la URL que imprime, reiniciar
   (`docker compose up -d`).
2. **También** hace falta un túnel para Keycloak — el canje de código→token
   de un custom connector remoto lo hace la nube de Anthropic, no el browser
   local, así que `token_endpoint`/`jwks_uri` tienen que ser públicos
   también: `cloudflared tunnel --url http://localhost:8080` → actualizar
   `KEYCLOAK_PUBLIC_URL` acá (`docker-compose.yml`, o `.env`) **y**
   `KC_HOSTNAME`/`KEYCLOAK_ISSUER_URL` en `personal-finance-service` (deben
   apuntar a la MISMA URL del túnel de Keycloak, si no el `issuer` del
   discovery document no coincide con el `iss` real del JWT).
3. Custom connector en Claude: URL `https://<túnel-mcp>/mcp`, Client ID
   `mcp-personal-finance-client`, sin secret.

Los túneles gratuitos de Cloudflare (`trycloudflare.com`) son efímeros — la
URL cambia cada vez que se reinicia `cloudflared`, y la conexión se cae sola
si la máquina se suspende. Hay que resincronizar las 3 variables de arriba
cada vez que eso pase. **No dejar ninguno de estos cambios commiteado** —
son puramente para probar en dev, revertir `KC_HOSTNAME`/`KEYCLOAK_ISSUER_URL`/
`KEYCLOAK_PUBLIC_URL` a `localhost` apenas termine la prueba.

## Conventions this repo follows

- **Skills**: `remote-mcp-keycloak` (estructura del proyecto, auth), `swagger-to-mcp-tools`
  (una tool por endpoint, agrupadas por tag en `src/mcp_handler/tools/`),
  `gitignore-agent-tooling` (`.claude/`, etc. gitignoreados).
- **`api-keys` de personal-finance-service NO se expone como tools** — dejar
  que un LLM cree/revoque sus propias credenciales es un riesgo innecesario.
- **Auth contra la REST API (Patrón C de `swagger-to-mcp-tools`)**: las tools
  reenvían el JWT crudo del caller humano (`request.state.raw_token`) tal
  cual a `personal-finance-service` — funciona porque comparten el mismo
  realm de Keycloak y `KeycloakAuthGuard` de esa API no valida `audience`,
  solo `issuer` + firma. El agente M2M no tiene un usuario real detrás de su
  token (es una service account), así que usa en su lugar una **Personal
  Finance API Key** fija (`UPSTREAM_API_KEY`), generada de antemano por un
  usuario real via `POST /api-keys` en `personal-finance-service`.
- **Naming de tools**: derivado del `operationId` de NestJS/Swagger
  (`GroupsController_search`), quitando el prefijo `XxxController_` y
  ajustando a snake_case legible (`search_groups`), no la regla genérica de
  `swagger-to-mcp-tools` (method+path) que da nombres menos claros acá.
- **Wire snake_case vs. swagger camelCase**: el swagger de
  `personal-finance-service` muestra los campos en camelCase (así están en
  TypeScript), pero el wire real es snake_case (`CaseConversionInterceptor`
  de esa API) — los bodies/params que arman las tools usan snake_case
  siempre, no lo que muestra el swagger literalmente.

## Non-obvious decisions (and why)

- **`mcp>=2.0` (MCPServer), no `mcp` 1.x (FastMCP)** — instalar sin pinnear
  resolvió la 2.x más reciente durante el desarrollo; el import correcto es
  `from mcp.server.mcpserver import MCPServer, Context`. Ver la nota en el
  skill `remote-mcp-keycloak` si esto vuelve a cambiar.
- **`register_mcp_lifespan()` copia rutas al router en vez de usar
  `app.mount('/mcp', ...)`** — un `Mount()` a un sub-path anida un router y
  el `redirect_slashes` de Starlette devuelve un 307 que un cliente MCP
  streaming no sigue. Verificado con un smoke test real (`docker build` +
  `curl`): boot limpio, `/health`/`/.well-known` en 200, `POST /mcp` sin
  token en 401 con `WWW-Authenticate` (sin 307 ni el error de TaskGroup).
- **`transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)`
  en `register_mcp_lifespan()`** — sin esto, `POST /mcp` responde `421 Invalid
  Host header` en cuanto el server corre detrás de cualquier proxy/túnel/load
  balancer (el SDK solo permite `Host: localhost/127.0.0.1/::1` por default).
  Encontrado probando un custom connector remoto real de Claude Desktop vía
  túnel cloudflared.
- **`CORSMiddleware` agregado después de `AuthMiddleware`** (en `main.py`) —
  sin esto, el preflight `OPTIONS /mcp` de un cliente remoto (Claude
  Desktop/claude.ai) recibe 401 de `AuthMiddleware` y el cliente lo ve como
  fallo de red genérico ("Couldn't connect"), nunca llega a mostrar el login
  de Keycloak. Encontrado en la misma prueba real de arriba.
- **Reusa el realm `personal-finance` de `personal-finance-service`**, no
  un realm propio — decisión explícita para habilitar el passthrough del
  JWT humano (ver Patrón C arriba). Si algún día `personal-finance-service`
  empieza a validar `audience` en su `KeycloakAuthGuard`, este passthrough
  deja de funcionar y hay que pasar a Patrón A (token estático) para todos
  los consumidores, no solo el agente.
- **El swagger de `personal-finance-service` estaba vacío de detalle**
  (`components.schemas` con `properties: {}` en todos los DTOs, sin
  parámetros de query en `search()`) hasta que se activó el plugin
  `@nestjs/swagger` en `nest-cli.json` de ese repo — sin eso, no había forma
  de derivar tipos/campos reales para las tools.
- **`close_expense_cycle` no es idempotente** (hereda esa limitación de
  `POST /expenses/close-cycle` en `personal-finance-service`) — llamarlo dos
  veces en el mismo ciclo de facturación genera dos cuotas.

## Known gaps (deliberately out of scope right now)

- Sin scheduler/cron — el agente M2M y `close_expense_cycle` son 100% disparo manual.
- `docker-compose.test.yml` (WireMock + Keycloak + pytest, skill
  `mcp-integration-tests`) todavía no generado.
- No hay CI configurado.

## Where to look next

- `README.md` — instrucciones de uso para un humano.
- `tests/keycloak/script/setup_keycloak_realm.py` — setup de Keycloak.
- `src/mcp_handler/tools/` — las 13 tools, agrupadas por tag (groups,
  payment_methods, expenses).

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    server_name: str
    server_url: str

    keycloak_realm_url: str
    keycloak_public_url: str = ""
    keycloak_client_id: str
    keycloak_client_secret: str

    # Client ID del client M2M — permite a las tools distinguir un caller
    # humano de un agente headless comparando contra claims["azp"].
    mcp_agent_client_id: str = ""

    # Patrón C (swagger-to-mcp-tools): API downstream que envuelven las tools.
    upstream_api_base_url: str = ""
    # Credencial estática (Personal Finance API Key) — solo la usa el agente
    # M2M, que no tiene un usuario humano real detrás de su token.
    upstream_api_key: str = ""

    @property
    def keycloak_discovery_url(self) -> str:
        return self.keycloak_public_url or self.keycloak_realm_url

    @property
    def jwks_uri(self) -> str:
        return f"{self.keycloak_realm_url}/protocol/openid-connect/certs"

    @property
    def jwt_issuer(self) -> str:
        return self.keycloak_discovery_url

    @property
    def jwt_audience(self) -> str:
        return self.keycloak_client_id

    class Config:
        env_file = ".env"

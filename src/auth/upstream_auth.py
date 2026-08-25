"""
Patrón C (skill swagger-to-mcp-tools): personal-finance-service comparte el
mismo realm de Keycloak que este MCP server, y su KeycloakAuthGuard no valida
`audience` — solo `issuer` + firma. Eso hace que el JWT que un usuario humano
obtiene al loguearse acá (emitido a mcp-personal-finance-client) sea también
un JWT válido contra la REST API tal cual, sin credencial separada.

El agente M2M (mcp-personal-finance-agent) no tiene un usuario real detrás —
su token es de una service account — así que no hay nada útil que reenviar:
usa en su lugar una Personal Finance API Key fija, provisionada de antemano
por un usuario real via POST /api-keys.
"""

from mcp.server.mcpserver import Context
from src.config import Settings


def resolve_upstream_token(ctx: Context | None, settings: Settings) -> str:
    if ctx is not None:
        state = ctx.request_context.request.state
        raw_token = getattr(state, "raw_token", None)
        claims = getattr(state, "user", None)
        is_agent = (
            claims is not None
            and settings.mcp_agent_client_id
            and claims.get("azp") == settings.mcp_agent_client_id
        )
        if raw_token and not is_agent:
            return raw_token

    if not settings.upstream_api_key:
        raise RuntimeError(
            "No hay JWT de usuario para reenviar ni upstream_api_key configurada "
            "(¿falta configurar la Personal Finance API Key del agente?)"
        )
    return settings.upstream_api_key

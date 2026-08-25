from contextlib import asynccontextmanager
from starlette.applications import Starlette
from mcp.server.mcpserver import MCPServer
from src.config import Settings


def create_mcp() -> MCPServer:
    """Instancia el MCPServer y registra las tools de negocio (my_tools.py)."""
    settings = Settings()
    mcp = MCPServer(name=settings.server_name)

    from src.mcp_handler.tools.my_tools import register_tools
    register_tools(mcp)
    return mcp


def register_mcp_lifespan(app: Starlette, mcp: MCPServer) -> None:
    """
    Fusiona la(s) ruta(s) de `mcp.streamable_http_app()` directamente en el
    router de `app` (nunca via Mount a un sub-path como '/mcp' — un Mount()
    ahí anida un segundo router y el redirect_slashes=True por default de
    Starlette devuelve un 307 en POST /mcp -> POST /mcp/, que un cliente MCP
    streaming no sigue) y envuelve el lifespan existente de `app` con el
    session_manager.run() de MCPServer, que inicializa el TaskGroup interno
    de las sesiones Streamable HTTP.

    stateless_http=True (no asume sesión pegajosa a un proceso, necesario si
    el server corre con más de un replica detrás de un load balancer) se pasa
    acá — en mcp>=2.0 es un parámetro de streamable_http_app()/run(), no del
    constructor de MCPServer.
    """
    mcp_app = mcp.streamable_http_app(stateless_http=True)
    app.router.routes.extend(mcp_app.routes)

    existing_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def combined_lifespan(app_):
        async with mcp.session_manager.run():
            async with existing_lifespan(app_):
                yield

    app.router.lifespan_context = combined_lifespan

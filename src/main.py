from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from src.auth.middleware import AuthMiddleware
from src.auth.oauth_discovery import oauth_discovery_metadata
from src.config import Settings
from src.mcp_handler.server import create_mcp, register_mcp_lifespan


async def health(request):
    return JSONResponse({"status": "ok", "server": Settings().server_name})


async def oauth_authorization_server(request):
    return JSONResponse(oauth_discovery_metadata(Settings()))


def create_app() -> Starlette:
    app = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route(
                "/.well-known/oauth-authorization-server",
                oauth_authorization_server,
                methods=["GET"],
            ),
        ],
    )
    app.add_middleware(AuthMiddleware)
    # Agregado DESPUÉS de AuthMiddleware -> queda como middleware más externo
    # (Starlette inserta cada add_middleware() al frente de la pila), así el
    # preflight CORS (OPTIONS) se resuelve antes de llegar a la validación de
    # auth. Sin esto, un cliente que hace preflight ve un 401 en el OPTIONS
    # y lo interpreta como fallo de red, no como "falta autenticarse".
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Mcp-Session-Id"],
        expose_headers=["Mcp-Session-Id", "WWW-Authenticate"],
    )

    register_mcp_lifespan(app, create_mcp())
    return app


app = create_app()

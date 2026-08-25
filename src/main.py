from starlette.applications import Starlette
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

    register_mcp_lifespan(app, create_mcp())
    return app


app = create_app()

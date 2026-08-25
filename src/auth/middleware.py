from starlette.requests import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse
from src.auth.token_validator import TokenValidator
from src.config import Settings

UNPROTECTED_PATHS = ["/.well-known/oauth-authorization-server", "/health"]


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, validator: TokenValidator = None):
        super().__init__(app)
        self.validator = validator or TokenValidator()
        self._settings = Settings()

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in UNPROTECTED_PATHS:
            return await call_next(request)

        metadata_url = f"{self._settings.server_url}/.well-known/oauth-authorization-server"
        www_auth = f'Bearer resource_metadata="{metadata_url}"'

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or malformed Authorization header"},
                headers={"WWW-Authenticate": www_auth},
            )

        token = auth_header.removeprefix("Bearer ").strip()
        claims, error_reason = await self.validator.validate(token)

        if claims is None:
            if error_reason == "expired":
                # Token expirado: 401 + WWW-Authenticate dispara re-autenticación en Kiro
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Token expired, re-authentication required"},
                    headers={"WWW-Authenticate": www_auth},
                )
            # Token inválido por otra razón (firma, audience, issuer)
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid token"},
            )

        request.state.user = claims
        request.state.raw_token = token
        return await call_next(request)

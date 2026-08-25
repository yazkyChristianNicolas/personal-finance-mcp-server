import httpx
from jose import jwt, JWTError
from src.config import Settings


class TokenValidator:
    def __init__(self, settings: Settings = None):
        self.settings = settings or Settings()
        self._jwks_cache: dict | None = None

    async def _get_jwks(self) -> dict:
        if self._jwks_cache is None:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.settings.jwks_uri)
                response.raise_for_status()
                self._jwks_cache = response.json()
        return self._jwks_cache

    async def validate(self, token: str) -> tuple[dict | None, str | None]:
        """
        Verifica firma RS256, audience, issuer y expiración.
        NO valida roles ni scopes — eso es responsabilidad de cada tool.

        Returns:
            (claims, None)        → token válido
            (None, "expired")     → token expirado — el cliente debe re-autenticarse
            (None, "invalid")     → token inválido (firma, audience, issuer, etc.)
        """
        try:
            jwks = await self._get_jwks()
            claims = jwt.decode(
                token,
                jwks,
                algorithms=["RS256"],
                audience=self.settings.jwt_audience,
                issuer=self.settings.jwt_issuer,
            )
            return claims, None
        except JWTError as e:
            error_str = str(e).lower()
            expired = "expired" in error_str or "expir" in error_str
            return None, "expired" if expired else "invalid"

    def has_scope(self, claims: dict, required_scope: str) -> bool:
        """Verifica si el token incluye un scope específico."""
        scopes = claims.get("scope", "").split()
        return required_scope in scopes

    def has_role(self, claims: dict, required_role: str, client_id: str = None) -> bool:
        """
        Verifica si el token incluye un rol de cliente específico.

        Keycloak incluye los roles en resource_access.{client_id}.roles
        automáticamente cuando el client scope 'roles' está asignado como
        default al public client. Son transparentes — no requieren que Kiro
        los solicite explícitamente.
        """
        target_client = client_id or self.settings.keycloak_client_id
        resource_access = claims.get("resource_access", {})
        client_roles = resource_access.get(target_client, {}).get("roles", [])
        return required_role in client_roles

    def has_scope_or_role(self, claims: dict, scope: str, role: str, client_id: str = None) -> bool:
        """
        Verifica acceso por scope O por rol de cliente.

        Usar este método en las tools:
        - Rol model: roles de Keycloak, transparentes (no requieren config en Kiro)
        - Scope model: scopes explícitos, útil para control más granular
        """
        return self.has_scope(claims, scope) or self.has_role(claims, role, client_id)

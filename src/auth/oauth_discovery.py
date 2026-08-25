from src.config import Settings


def oauth_discovery_metadata(settings: Settings) -> dict:
    base = settings.keycloak_discovery_url
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/protocol/openid-connect/auth",
        "token_endpoint": f"{base}/protocol/openid-connect/token",
        "jwks_uri": f"{base}/protocol/openid-connect/certs",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    }

"""
Helper HTTP compartido por las tools — no es una tool en sí (no se registra
en FastMCP), solo evita repetir la resolución de auth (Patrón C) y el manejo
de respuestas en cada tool.
"""

import httpx
from mcp.server.mcpserver import Context
from src.auth.upstream_auth import resolve_upstream_token
from src.config import Settings


async def call_api(
    ctx: Context | None,
    method: str,
    path: str,
    json: dict | None = None,
    params: dict | None = None,
) -> dict:
    settings = Settings()
    token = resolve_upstream_token(ctx, settings)

    async with httpx.AsyncClient(base_url=settings.upstream_api_base_url) as client:
        response = await client.request(
            method,
            path,
            headers={"Authorization": f"Bearer {token}"},
            json=json,
            params=params,
        )

        # personal-finance-service devuelve application/problem+json en errores
        # (status/detail/instance) — se lo pasamos al LLM tal cual en vez de
        # levantar una excepción, así puede explicarle el motivo al usuario.
        if response.status_code == 204:
            return {"status": "deleted"}
        return response.json()

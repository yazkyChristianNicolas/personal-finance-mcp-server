from mcp.server.mcpserver import MCPServer, Context
from src.mcp_handler.tools._client import call_api


def register_groups_tools(mcp: MCPServer):

    @mcp.tool()
    async def search_groups(
        page: int | None = None,
        size: int | None = None,
        ctx: Context | None = None,
    ) -> dict:
        """Lista los grupos del usuario autenticado (siempre incluye su grupo Personal).

        Usar cuando el usuario pregunte qué grupos tiene, o antes de crear un
        gasto compartido para saber a qué grupo asignarlo.

        Args:
            page: Página a traer, 1-indexada (default: 1)
            size: Cantidad de resultados por página (default: 20)

        Returns:
            dict con `data` (lista de {id, name, is_default}) y `meta` de paginación
        """
        params = {k: v for k, v in {"page": page, "size": size}.items() if v is not None}
        return await call_api(ctx, "GET", "/groups", params=params)

    @mcp.tool()
    async def create_group(
        name: str,
        ctx: Context | None = None,
    ) -> dict:
        """Crea un grupo nuevo (ej. para compartir gastos con roommates o familia).

        Args:
            name: Nombre del grupo (máximo 120 caracteres)

        Returns:
            dict con el grupo creado: {id, name, is_default}
        """
        return await call_api(ctx, "POST", "/groups", json={"name": name})

    @mcp.tool()
    async def search_group_members(
        group_id: str,
        page: int | None = None,
        size: int | None = None,
        ctx: Context | None = None,
    ) -> dict:
        """Lista los miembros de un grupo.

        Usar cuando haga falta saber quién forma parte de un grupo antes de
        dividir un gasto (split_strategy=PERCENTAGE o ROMANA en create_expense).

        Args:
            group_id: ID del grupo
            page: Página a traer, 1-indexada (default: 1)
            size: Cantidad de resultados por página (default: 20)

        Returns:
            dict con `data` (lista de {id, user_id, role, email, display_name}) y `meta`
        """
        params = {k: v for k, v in {"page": page, "size": size}.items() if v is not None}
        return await call_api(ctx, "GET", f"/groups/{group_id}/members", params=params)

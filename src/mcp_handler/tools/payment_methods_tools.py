from typing import Literal
from mcp.server.mcpserver import MCPServer, Context
from src.mcp_handler.tools._client import call_api

PaymentMethodType = Literal["CASH", "DEBIT", "CREDIT"]


def register_payment_methods_tools(mcp: MCPServer):

    @mcp.tool()
    async def search_payment_methods(
        page: int | None = None,
        size: int | None = None,
        ctx: Context | None = None,
    ) -> dict:
        """Lista los medios de pago del usuario autenticado.

        Usar cuando el usuario pregunte con qué tarjetas/efectivo cuenta, o
        antes de crear un gasto para saber a qué payment_method_id asignarlo.

        Args:
            page: Página a traer, 1-indexada (default: 1)
            size: Cantidad de resultados por página (default: 20)

        Returns:
            dict con `data` (lista de {id, name, type}) y `meta` de paginación
        """
        params = {k: v for k, v in {"page": page, "size": size}.items() if v is not None}
        return await call_api(ctx, "GET", "/payment-methods", params=params)

    @mcp.tool()
    async def create_payment_method(
        name: str,
        type: PaymentMethodType,
        billing_cycle_start: int | None = None,
        billing_cycle_end: int | None = None,
        ctx: Context | None = None,
    ) -> dict:
        """Crea un medio de pago (efectivo, débito o tarjeta de crédito).

        Args:
            name: Nombre descriptivo (ej. "Tarjeta Visa", "Efectivo")
            type: CASH=efectivo, DEBIT=débito, CREDIT=tarjeta de crédito
            billing_cycle_start: Día del mes en que arranca el ciclo de resumen
                (1-31). Solo aplica y se persiste si type=CREDIT.
            billing_cycle_end: Día del mes en que corta el ciclo de resumen
                (1-31). Solo aplica y se persiste si type=CREDIT.

        Returns:
            dict con el medio de pago creado: {id, name, type, billing_cycle_start, billing_cycle_end}
        """
        body = {"name": name, "type": type}
        if billing_cycle_start is not None:
            body["billing_cycle_start"] = billing_cycle_start
        if billing_cycle_end is not None:
            body["billing_cycle_end"] = billing_cycle_end
        return await call_api(ctx, "POST", "/payment-methods", json=body)

    @mcp.tool()
    async def patch_payment_method(
        payment_method_id: str,
        name: str | None = None,
        type: PaymentMethodType | None = None,
        billing_cycle_start: int | None = None,
        billing_cycle_end: int | None = None,
        ctx: Context | None = None,
    ) -> dict:
        """Modifica parcialmente un medio de pago existente.

        Solo se actualizan los campos provistos. Si se cambia type a algo
        distinto de CREDIT, billing_cycle_start/end se limpian del lado del
        servidor automáticamente.

        Args:
            payment_method_id: ID del medio de pago a modificar
            name: Nuevo nombre (opcional)
            type: Nuevo tipo — CASH, DEBIT o CREDIT (opcional)
            billing_cycle_start: Nuevo día de inicio de ciclo, 1-31 (opcional, solo CREDIT)
            billing_cycle_end: Nuevo día de cierre de ciclo, 1-31 (opcional, solo CREDIT)

        Returns:
            dict con el medio de pago actualizado
        """
        body = {}
        if name is not None:
            body["name"] = name
        if type is not None:
            body["type"] = type
        if billing_cycle_start is not None:
            body["billing_cycle_start"] = billing_cycle_start
        if billing_cycle_end is not None:
            body["billing_cycle_end"] = billing_cycle_end
        return await call_api(ctx, "PATCH", f"/payment-methods/{payment_method_id}", json=body)

    @mcp.tool()
    async def delete_payment_method(
        payment_method_id: str,
        ctx: Context | None = None,
    ) -> dict:
        """Elimina un medio de pago.

        Args:
            payment_method_id: ID del medio de pago a eliminar

        Returns:
            dict con status de la operación (ej: {"status": "deleted"})
        """
        return await call_api(ctx, "DELETE", f"/payment-methods/{payment_method_id}")

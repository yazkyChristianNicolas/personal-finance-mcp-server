from typing import Literal
from mcp.server.mcpserver import MCPServer, Context
from src.mcp_handler.tools._client import call_api

SplitStrategy = Literal["EQUAL", "PERCENTAGE", "ROMANA"]


def register_expenses_tools(mcp: MCPServer):

    @mcp.tool()
    async def search_expenses(
        page: int | None = None,
        size: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        group_id: str | None = None,
        category: str | None = None,
        payment_method_id: str | None = None,
        currency: str | None = None,
        ctx: Context | None = None,
    ) -> dict:
        """Lista gastos, filtrando opcionalmente por grupo, categoría, medio de
        pago, moneda o rango de fechas.

        Sin group_id, trae gastos de TODOS los grupos del usuario. El objeto
        devuelto por gasto es minificado (sin splits) — usar get_expense para
        el detalle completo de uno puntual.

        Args:
            page: Página a traer, 1-indexada (default: 1)
            size: Cantidad de resultados por página (default: 20)
            date_from: Fecha desde (ISO 8601, ej: "2026-01-01"), inclusive
            date_to: Fecha hasta (ISO 8601, ej: "2026-01-31"), inclusive
            group_id: Filtrar por un grupo puntual (si no se especifica, todos)
            category: Filtrar por categoría (ej: "groceries", "tech")
            payment_method_id: Filtrar por medio de pago
            currency: Filtrar por moneda ISO 4217 (ej: "ARS", "USD")

        Returns:
            dict con `data` (lista de {id, date, amount, currency, description,
            category, group_id}) y `meta` de paginación
        """
        params = {
            k: v
            for k, v in {
                "page": page,
                "size": size,
                "date_from": date_from,
                "date_to": date_to,
                "group_id": group_id,
                "category": category,
                "payment_method_id": payment_method_id,
                "currency": currency,
            }.items()
            if v is not None
        }
        return await call_api(ctx, "GET", "/expenses", params=params)

    @mcp.tool()
    async def create_expense(
        date: str,
        amount: int,
        currency: str,
        description: str,
        category: str,
        group_id: str,
        payment_method_id: str,
        split_strategy: SplitStrategy | None = None,
        split_members: list[dict] | None = None,
        installments_count: int | None = None,
        ctx: Context | None = None,
    ) -> dict:
        """Registra un gasto nuevo, opcional en cuotas y/o dividido entre miembros de un grupo.

        Si group_id NO es el grupo Personal del usuario, split_strategy es
        obligatorio. Con installments_count, `amount` pasa a ser el TOTAL de
        la compra (no el monto de este registro): el monto que efectivamente
        se persiste (y se splittea, si aplica) es total/installments_count —
        la última cuota absorbe el resto de la división y se genera recién
        cuando se llama a close_expense_cycle.

        Args:
            date: Fecha del gasto, ISO 8601 (ej: "2026-08-20")
            amount: Monto en centavos (150000 = $1500.00). Si installments_count
                está presente, este es el TOTAL de la compra, no la cuota.
            currency: Moneda ISO 4217 (ej: "ARS", "USD")
            description: Descripción del gasto (ej: "Supermercado")
            category: Categoría libre (ej: "groceries", "tech", "utilities")
            group_id: Grupo al que pertenece el gasto (usar search_groups)
            payment_method_id: Medio de pago usado (usar search_payment_methods).
                Si se pasa installments_count, debe ser una tarjeta CREDIT.
            split_strategy: EQUAL=partes iguales entre todos los miembros del
                grupo, PERCENTAGE=por porcentaje explícito por miembro,
                ROMANA=por monto explícito por miembro. Requerido si group_id
                no es el grupo Personal.
            split_members: Lista de {"user_id": str, "percentage": float} para
                PERCENTAGE (deben sumar 100), o {"user_id": str, "amount": int}
                para ROMANA (deben sumar exactamente el monto del gasto — o de
                la cuota, si hay installments_count). No se usa para EQUAL.
            installments_count: Cantidad de cuotas (mínimo 2). Si se omite, el
                gasto es en un solo pago.

        Returns:
            dict con el gasto creado — incluye installment_number/
            installments_count/installments_total_amount si es en cuotas, y
            `splits` (lista de {user_id, amount, percentage}) si se dividió
        """
        body = {
            "date": date,
            "amount": amount,
            "currency": currency,
            "description": description,
            "category": category,
            "group_id": group_id,
            "payment_method_id": payment_method_id,
        }
        if split_strategy is not None:
            body["split_strategy"] = split_strategy
        if split_members is not None:
            body["split_members"] = split_members
        if installments_count is not None:
            body["installments_count"] = installments_count
        return await call_api(ctx, "POST", "/expenses", json=body)

    @mcp.tool()
    async def close_expense_cycle(
        payment_method_id: str,
        ctx: Context | None = None,
    ) -> dict:
        """Cierra el ciclo de facturación de una tarjeta CREDIT: genera la
        cuota siguiente de cada gasto en cuotas activo de esa tarjeta.

        Disparo MANUAL — llamar solo cuando realmente cortó el ciclo de la
        tarjeta (billing_cycle_end en payment-methods). No es idempotente:
        llamarlo dos veces en el mismo ciclo genera dos cuotas para el mismo
        período. Falla si el medio de pago no es CREDIT o no es del usuario.

        Args:
            payment_method_id: ID de la tarjeta CREDIT cuyo ciclo cortó

        Returns:
            dict con `generated_expenses` (lista de los gastos de la cuota
            siguiente generados — vacía si no había ningún plan de cuotas activo)
        """
        return await call_api(
            ctx, "POST", "/expenses/close-cycle", json={"payment_method_id": payment_method_id}
        )

    @mcp.tool()
    async def get_expense(
        expense_id: str,
        ctx: Context | None = None,
    ) -> dict:
        """Obtiene el detalle completo de un gasto, incluidos sus splits.

        Args:
            expense_id: ID del gasto

        Returns:
            dict con todos los campos del gasto y `splits` (lista de
            {user_id, amount, percentage} por cada miembro que participa)
        """
        return await call_api(ctx, "GET", f"/expenses/{expense_id}")

    @mcp.tool()
    async def patch_expense(
        expense_id: str,
        date: str | None = None,
        amount: int | None = None,
        currency: str | None = None,
        description: str | None = None,
        category: str | None = None,
        payment_method_id: str | None = None,
        ctx: Context | None = None,
    ) -> dict:
        """Modifica parcialmente un gasto existente.

        Solo se actualizan los campos provistos. No se puede cambiar el
        grupo ni la estrategia de split de un gasto ya creado. Tampoco se
        puede cambiar `amount` de un gasto que es parte de un plan de
        cuotas (falla con 400) — corregir un monto en cuotas no está
        soportado todavía.

        Args:
            expense_id: ID del gasto a modificar
            date: Nueva fecha, ISO 8601 (opcional)
            amount: Nuevo monto en centavos (opcional, no válido si el gasto
                es en cuotas)
            currency: Nueva moneda ISO 4217 (opcional)
            description: Nueva descripción (opcional)
            category: Nueva categoría (opcional)
            payment_method_id: Nuevo medio de pago (opcional)

        Returns:
            dict con el gasto actualizado
        """
        body = {}
        if date is not None:
            body["date"] = date
        if amount is not None:
            body["amount"] = amount
        if currency is not None:
            body["currency"] = currency
        if description is not None:
            body["description"] = description
        if category is not None:
            body["category"] = category
        if payment_method_id is not None:
            body["payment_method_id"] = payment_method_id
        return await call_api(ctx, "PATCH", f"/expenses/{expense_id}", json=body)

    @mcp.tool()
    async def delete_expense(
        expense_id: str,
        ctx: Context | None = None,
    ) -> dict:
        """Elimina un gasto. Cualquier miembro del grupo puede hacerlo, no
        solo quien lo creó.

        Args:
            expense_id: ID del gasto a eliminar

        Returns:
            dict con status de la operación (ej: {"status": "deleted"})
        """
        return await call_api(ctx, "DELETE", f"/expenses/{expense_id}")

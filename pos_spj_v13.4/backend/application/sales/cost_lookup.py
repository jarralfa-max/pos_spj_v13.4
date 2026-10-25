"""Costo unitario de los productos de una venta (extraído del cobro el
2026-10-22, auditoría Fidelidad 968e0bc FID-03): el cobro lo usa para la salida
de inventario y el costo de venta, y el presupuesto de beneficios para no
regalar más margen del que hay. UNA sola regla de costo, no dos.

Un producto nunca costeado queda fuera y se informa: el costo no se inventa
(§18). Un COMPUESTO (receta de venta o combo de Productos) cuesta lo que
cuestan sus componentes; si a uno le falta costo, al compuesto también.
"""

from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger("spj.sales.cost_lookup")


def sale_unit_costs(connection, sale, *, costs=None, virtual: dict | None = None
                    ) -> tuple[dict, list[str]]:
    """(costo unitario por producto, productos sin costo)."""
    from backend.application.products.queries.sales_fulfillment_query_service import (
        CompositeDefinitionError,
        SalesFulfillmentQueryService,
    )

    if costs is None:
        from backend.infrastructure.integrations.sales_pricing_client import (
            SalesPricingClient,
        )
        costs = SalesPricingClient(connection)
    composicion = SalesFulfillmentQueryService(connection)

    def costo_de(product_id):
        try:
            costo = costs.unit_cost(product_id, branch_id=sale.branch_id)
        except Exception:
            logger.exception("costo de %s no disponible", product_id)
            return None
        return None if costo is None else Decimal(str(costo))

    costos: dict[str, Decimal] = {}
    sin_costo: set[str] = set()
    virtual = virtual or {}
    cantidades: dict[str, Decimal] = {}
    for line in sale.goods_lines:
        cantidades[line.product_id] = cantidades.get(
            line.product_id, Decimal("0")) + line.quantity.value
    for product_id in {line.product_id for line in sale.goods_lines}:
        if product_id in virtual:
            # Composición virtual (integración Logística 32cfbf): la línea
            # cuesta su parte directa a su costo y el faltante a lo que
            # cuestan las partes con que se surte.
            partes = dict(virtual[product_id])
            faltante = partes.pop("__shortfall__")
            total, completo = Decimal("0"), True
            for parte, cantidad in partes.items():
                costo = costo_de(parte)
                if costo is None:
                    sin_costo.add(parte)
                    completo = False
                    continue
                costos[parte] = costo
                total += cantidad * costo
            directo = cantidades[product_id] - faltante
            if directo > 0:
                propio = costo_de(product_id)
                if propio is None:
                    completo = False
                else:
                    total += directo * propio
            if completo and cantidades[product_id] > 0:
                costos[product_id] = total / cantidades[product_id]
            else:
                sin_costo.add(product_id)
            continue
        try:
            partes = composicion.explode(product_id, Decimal("1"))
        except CompositeDefinitionError:
            # Composición inválida en Productos: sin costo, no inventado.
            sin_costo.add(product_id)
            continue
        if set(partes) == {product_id}:
            costo = costo_de(product_id)
            if costo is None:
                sin_costo.add(product_id)
            else:
                costos[product_id] = costo
            continue
        total = Decimal("0")
        completo = True
        for componente, cantidad in partes.items():
            costo = costo_de(componente)
            if costo is None:
                sin_costo.add(componente)
                completo = False
                continue
            costos[componente] = costo
            total += cantidad * costo
        if completo:
            costos[product_id] = total
        else:
            sin_costo.add(product_id)
    return costos, sorted(sin_costo)

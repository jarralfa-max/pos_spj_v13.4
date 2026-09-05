"""Read-only price/quantity OBSERVATION history for pricing-elasticity
estimation (BI-16/BI-27). Reads the same `detalles_venta`/`ventas` tables
`BiSalesQueryService` already reads: one (price, quantity) point per day the
product actually sold at a given unit price.

Not the same concern as `PricingReadService.list_price_history()`
(`backend/application/pricing/`) — that reads `price_change_log`, a log of
price-LIST edits (old/new value, who authorized it); this reads what price
customers were actually charged and how much they bought at it, the input
`estimate_price_elasticity` (BI-16) needs.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("spj.bi.price_history")

_COST_JOIN = ("LEFT JOIN product_cost pcost "
              "ON pcost.product_id=dv.producto_id AND pcost.branch_id=''")


class PriceHistoryQueryService:
    def __init__(self, conn):
        self._conn = conn

    def price_quantity_history(self, *, product_id: str, branch_id: str | None = None,
                                limit: int = 200) -> list[tuple[float, float]]:
        """One (precio_unitario, cantidad vendida ese día a ese precio) por
        fila — nunca None (§16's `estimate_price_elasticity` filtra sus
        propios puntos inválidos)."""
        sql = ("SELECT dv.precio_unitario, SUM(dv.cantidad) "
               "FROM detalles_venta dv JOIN ventas v ON v.id=dv.venta_id "
               "WHERE v.estado='completada' AND dv.producto_id=? "
               "AND dv.precio_unitario IS NOT NULL")
        params: list = [product_id]
        if branch_id:
            sql += " AND v.sucursal_id=?"
            params.append(str(branch_id))
        sql += (" GROUP BY DATE(v.fecha), dv.precio_unitario "
                "ORDER BY v.fecha DESC LIMIT ?")
        params.append(int(limit))
        try:
            rows = self._conn.execute(sql, params).fetchall()
            return [(float(r[0]), float(r[1] or 0)) for r in rows]
        except Exception as e:
            logger.warning("price_quantity_history: %s", e)
            return []

    def latest_price(self, *, product_id: str, branch_id: str | None = None) -> float | None:
        sql = ("SELECT dv.precio_unitario FROM detalles_venta dv "
               "JOIN ventas v ON v.id=dv.venta_id "
               "WHERE v.estado='completada' AND dv.producto_id=? "
               "AND dv.precio_unitario IS NOT NULL")
        params: list = [product_id]
        if branch_id:
            sql += " AND v.sucursal_id=?"
            params.append(str(branch_id))
        sql += " ORDER BY v.fecha DESC LIMIT 1"
        try:
            row = self._conn.execute(sql, params).fetchone()
            return float(row[0]) if row else None
        except Exception as e:
            logger.warning("latest_price: %s", e)
            return None

    def current_cost(self, *, product_id: str) -> float | None:
        try:
            row = self._conn.execute(
                "SELECT average_cost FROM product_cost WHERE product_id=? AND branch_id=''",
                [product_id]).fetchone()
            return float(row[0]) if row and row[0] is not None else None
        except Exception as e:
            logger.warning("current_cost: %s", e)
            return None

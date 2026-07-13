"""Read-only BI query service for inventory metrics: valuation, waste, critical stock.

Inventory quantities come from the branch-specific inventory_stock table (never
productos.existencia, which is a global sum). Waste comes from the mermas table.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("spj.bi.inventory")

# Product cost fallback chain (no captured line cost here).
_PROD_COST = "COALESCE(NULLIF(p.costo,0), NULLIF(p.precio_compra,0), NULLIF(p.costo_promedio,0), 0)"


class BiInventoryQueryService:
    def __init__(self, conn):
        self._conn = conn

    def _scalar(self, sql, params=()) -> float:
        try:
            row = self._conn.execute(sql, params).fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0
        except Exception as e:
            logger.warning("BiInventoryQueryService: %s", e)
            return 0.0

    def inventory_valued(self, f) -> float:
        """Inventario valorizado = sum(existencia_sucursal * costo_producto)."""
        sql = (f"SELECT COALESCE(SUM(ist.quantity * {_PROD_COST}),0) "
               "FROM inventory_stock ist JOIN productos p ON p.id = ist.product_id "
               "WHERE COALESCE(p.activo,1)=1")
        params: list = []
        if f.branch_id:
            sql += " AND ist.branch_id = ?"
            params.append(str(f.branch_id))
        return self._scalar(sql, params)

    def waste_value(self, f) -> float:
        """Costo estimado de merma del periodo (mermas.valor_perdida)."""
        sql = ("SELECT COALESCE(SUM(COALESCE(valor_perdida, cantidad*COALESCE(costo_unitario,0))),0) "
               "FROM mermas WHERE DATE(COALESCE(fecha, created_at)) BETWEEN ? AND ?")
        params: list = [f.date_from, f.date_to]
        if f.branch_id:
            sql += " AND sucursal_id = ?"
            params.append(str(f.branch_id))
        return self._scalar(sql, params)

    def critical_stock(self, f, limit: int = 15) -> list[dict]:
        """Productos por debajo o al nivel de su stock mínimo (por sucursal)."""
        sql = ("SELECT p.nombre, ist.quantity, COALESCE(p.stock_minimo,0), COALESCE(p.unidad,'') "
               "FROM inventory_stock ist JOIN productos p ON p.id = ist.product_id "
               "WHERE COALESCE(p.activo,1)=1 AND COALESCE(p.stock_minimo,0) > 0 "
               "AND ist.quantity <= p.stock_minimo")
        params: list = []
        if f.branch_id:
            sql += " AND ist.branch_id = ?"
            params.append(str(f.branch_id))
        sql += " ORDER BY (ist.quantity - p.stock_minimo) ASC LIMIT ?"
        params.append(limit)
        try:
            rows = self._conn.execute(sql, params).fetchall()
            return [{"nombre": r[0], "existencia": float(r[1] or 0),
                     "stock_minimo": float(r[2] or 0), "unidad": r[3]} for r in rows]
        except Exception as e:
            logger.warning("critical_stock: %s", e)
            return []

    def waste_by_category(self, f) -> list[tuple[str, float]]:
        sql = ("SELECT COALESCE(NULLIF(p.categoria,''),'(sin categoría)') c, "
               "COALESCE(SUM(COALESCE(m.valor_perdida, m.cantidad*COALESCE(m.costo_unitario,0))),0) v "
               "FROM mermas m LEFT JOIN productos p ON p.id=m.producto_id "
               "WHERE DATE(COALESCE(m.fecha, m.created_at)) BETWEEN ? AND ? ")
        params: list = [f.date_from, f.date_to]
        if f.branch_id:
            sql += "AND m.sucursal_id = ? "
            params.append(str(f.branch_id))
        sql += "GROUP BY c ORDER BY v DESC LIMIT 10"
        try:
            return [(r[0], float(r[1] or 0)) for r in self._conn.execute(sql, params).fetchall()]
        except Exception as e:
            logger.warning("waste_by_category: %s", e)
            return []

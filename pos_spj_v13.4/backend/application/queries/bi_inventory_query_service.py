"""Read-only BI query service for inventory metrics: valuation, waste, critical stock.

Inventory quantities come from the branch-specific on-hand source (never a global
product-level sum). Name, active state, category, unit, cost and minimum stock come
from the canonical master/catalogs (`products`, `product_categories`,
`units_of_measure`, `product_cost`, `inventory_replenishment_rule`). Waste value
comes from the mermas table.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("spj.bi.inventory")

# Costo de producto canónico (`product_cost`, sucursal global branch_id=''). El
# maestro `products` NO guarda costo (§11); el valor promedio vive en product_cost.
_PROD_COST = "COALESCE(NULLIF(CAST(pcost.average_cost AS REAL),0), 0)"


# Canonical on-hand source (INV-27): a subquery exposing ist.product_id/branch_id/
# quantity from inventory_balances, so the BI SQL is unchanged apart from the FROM.
_CANONICAL_STOCK = (
    "(SELECT product_id, branch_id,"
    " SUM(CAST(quantity AS REAL)) AS quantity FROM inventory_balances"
    " WHERE inventory_status='AVAILABLE' GROUP BY product_id, branch_id)")


class BiInventoryQueryService:
    def __init__(self, conn):
        self._conn = conn

    def _stock_source(self) -> str:
        """FROM fragment for on-hand stock: canonical projection when the cutover
        flag is ON, legacy inventory_stock while OFF (reads follow writes)."""
        try:
            from backend.application.inventory.cutover import is_cutover_enabled
            if is_cutover_enabled(self._conn):
                return _CANONICAL_STOCK
        except Exception:
            pass
        return "inventory_stock"

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
               f"FROM {self._stock_source()} ist JOIN products p ON p.id = ist.product_id "
               "LEFT JOIN product_cost pcost ON pcost.product_id=p.id AND pcost.branch_id='' "
               "WHERE p.lifecycle_status='ACTIVE'")
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
        # Nombre/unidad canónicos (products/units_of_measure); stock mínimo desde la
        # regla de reposición global (`inventory_replenishment_rule`, branch/warehouse
        # vacíos). El maestro `products` no guarda stock_minimo ni unidad como texto.
        sql = ("SELECT p.name, ist.quantity, COALESCE(CAST(rr.min_quantity AS REAL),0), "
               "COALESCE(u.code,'') "
               f"FROM {self._stock_source()} ist JOIN products p ON p.id = ist.product_id "
               "LEFT JOIN inventory_replenishment_rule rr ON rr.product_id=p.id "
               "AND rr.branch_id='' AND rr.warehouse_id='' "
               "LEFT JOIN units_of_measure u ON u.id=p.base_unit_id "
               "WHERE p.lifecycle_status='ACTIVE' "
               "AND COALESCE(CAST(rr.min_quantity AS REAL),0) > 0 "
               "AND ist.quantity <= CAST(rr.min_quantity AS REAL)")
        params: list = []
        if f.branch_id:
            sql += " AND ist.branch_id = ?"
            params.append(str(f.branch_id))
        sql += " ORDER BY (ist.quantity - CAST(rr.min_quantity AS REAL)) ASC LIMIT ?"
        params.append(limit)
        try:
            rows = self._conn.execute(sql, params).fetchall()
            return [{"nombre": r[0], "existencia": float(r[1] or 0),
                     "stock_minimo": float(r[2] or 0), "unidad": r[3]} for r in rows]
        except Exception as e:
            logger.warning("critical_stock: %s", e)
            return []

    def waste_by_category(self, f) -> list[tuple[str, float]]:
        sql = ("SELECT COALESCE(NULLIF(pcat.name,''),'(sin categoría)') c, "
               "COALESCE(SUM(COALESCE(m.valor_perdida, m.cantidad*COALESCE(m.costo_unitario,0))),0) v "
               "FROM mermas m LEFT JOIN products p ON p.id=m.producto_id "
               "LEFT JOIN product_categories pcat ON pcat.id=p.category_id "
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

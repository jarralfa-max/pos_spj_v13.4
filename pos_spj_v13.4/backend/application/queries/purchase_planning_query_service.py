"""Read-only QueryService for the purchase planning UI/API read models."""

from __future__ import annotations

from typing import Any

from backend.application.queries.base_query_service import BaseQueryService, KpiMetric, QueryFilters, SearchResult, TableRow


class PurchasePlanningQueryService(BaseQueryService):
    scope = "purchase_planning"

    def search_purchase_plans(self, query: str, filters: QueryFilters | None = None) -> list[SearchResult]:
        return list(self.search(query, filters))

    def list_for_table(self, filters: QueryFilters | None = None) -> list[TableRow]:
        return list(self.list_rows(filters))

    def get_kpis(self, filters: QueryFilters | None = None) -> list[KpiMetric]:
        return list(self.metrics(filters))


class PurchasePlanningReadService:
    """
    Lecturas SQL de Planeación de Compras / Forecast para la UI PyQt.

    Ruta canónica: la pantalla de planeación NO ejecuta SQL; consume este
    servicio. Todos los identificadores son UUID strings.
    """

    def __init__(self, db_conn: Any) -> None:
        self.db = db_conn

    def list_forecastable_products(self, branch_id: str = "") -> list[dict]:
        """Productos comprables candidatos a forecast: [{id, nombre}, ...].

        Repunte P0-B: usa la búsqueda canónica de productos comprables
        (`SearchPurchasableProductsQueryService`) en vez de la tabla legacy
        `productos`. El backfill 148 fijó `purchasable=1`, así que el conjunto es
        equivalente para datos existentes."""
        from backend.application.products.queries.product_selection_query_service import (
            SearchPurchasableProductsQueryService,
        )
        rows = SearchPurchasableProductsQueryService(self.db).search(
            active_only=True, limit=100000)
        return [{"id": r.product_id, "nombre": r.name} for r in rows]

    def last_purchase_cost(self, product_id: str, branch_id: str = "") -> float:
        """Último costo de compra del producto (0.0 si no hay compras)."""
        product_id = str(product_id or "").strip()
        if not product_id:
            return 0.0
        row = self.db.execute(
            """SELECT dd.precio_unitario
               FROM detalles_compra dd
               JOIN compras c ON c.id = dd.compra_id
               WHERE dd.producto_id = ?
               ORDER BY c.fecha DESC LIMIT 1""",
            (product_id,),
        ).fetchone()
        return float(row[0] or 0) if row else 0.0

    def sales_history(self, product_id: str, branch_id: str, days: int) -> list[dict]:
        """Ventas diarias del producto: [{fecha, total_vendido}, ...]."""
        rows = self.db.execute(
            """SELECT date(v.fecha) AS fecha, SUM(d.cantidad) AS total_vendido
               FROM ventas v
               JOIN detalles_venta d ON v.id = d.venta_id
               WHERE d.producto_id = ?
                 AND v.sucursal_id = ?
                 AND v.estado = 'completada'
                 AND v.fecha >= date('now', ?)
               GROUP BY date(v.fecha)
               ORDER BY date(v.fecha) ASC""",
            (str(product_id), str(branch_id), f"-{int(days)} days"),
        ).fetchall()
        return [{"fecha": r[0], "total_vendido": float(r[1] or 0)} for r in rows]

    def current_stock(self, product_id: str, branch_id: str = "") -> float:
        """Existencia actual del producto (disponible canónico).

        Repunte P0-B/INV-27: lee `inventory_balances` vía
        `CanonicalStockReadAdapter` (gated) en vez de `productos.existencia`. Sin
        sucursal agrega todas las sucursales (equivalente al cache legacy)."""
        from core.services.inventory.canonical_stock_read_adapter import (
            CanonicalStockReadAdapter,
        )
        return CanonicalStockReadAdapter(lambda: self.db).available_float(
            str(product_id), str(branch_id) or None)

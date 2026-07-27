"""Production query services — read-only queries for the production UI/API."""

from __future__ import annotations

import logging
from typing import Any

import core.services.production_query_service as _core_pqs

logger = logging.getLogger("spj.queries.production")


class MeatProductionQueryService:
    """Backend-layer read model for meat production queries.

    Delegates to core.services.production_query_service so all SQL stays
    in one place.  UI modules import this class, not the core module directly.
    """

    def __init__(self, connection: Any) -> None:
        self._db = connection

    @classmethod
    def from_connection(cls, connection: Any) -> "MeatProductionQueryService":
        return cls(connection)

    def list_active_products(self) -> list[dict]:
        """Return active products as {id, nombre} for the carnica search widget."""
        return _core_pqs.get_productos_activos(self._db)

    def list_carnica_history(self, limit: int = 100) -> list[dict]:
        """Return carnica batch history rows: fecha, producto, peso_bruto, merma, peso_neto."""
        return _core_pqs.get_historial_carnica(self._db, limit=limit)

    def get_recipe_by_product_id(self, product_id: str) -> dict | None:
        """Return {id, nombre_receta} for the active recipe of a product, or None."""
        return _core_pqs.get_receta_by_product_id(self._db, product_id)

    def list_recipes_for_combo(self) -> list[dict]:
        """Return recipes for QComboBox population."""
        return _core_pqs.get_recetas_for_combo(self._db)

    def get_daily_kpis(self, branch_id: str = "", date: str | None = None) -> dict:
        """Return daily production KPIs."""
        return _core_pqs.get_daily_kpis(self._db, branch_id=branch_id, date=date)


# ---------------------------------------------------------------------------
# Backward-compatible shell (imported by __init__.py)
# ---------------------------------------------------------------------------
from backend.application.queries.base_query_service import BaseQueryService, KpiMetric, QueryFilters, SearchResult, TableRow


class ProductionQueryService(BaseQueryService):
    scope = "production"

    def search_production_runs(self, query: str, filters: QueryFilters | None = None) -> list[SearchResult]:
        return list(self.search(query, filters))

    def list_for_table(self, filters: QueryFilters | None = None) -> list[TableRow]:
        return list(self.list_rows(filters))

    def get_kpis(self, filters: QueryFilters | None = None) -> list[KpiMetric]:
        return list(self.metrics(filters))

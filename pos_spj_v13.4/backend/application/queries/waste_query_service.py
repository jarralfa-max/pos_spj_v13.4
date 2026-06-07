"""Read-only QueryService for the waste UI/API read models."""

from __future__ import annotations

import inspect

from backend.application.queries.base_query_service import BaseQueryService, KpiMetric, QueryFilters, SearchResult, TableRow


class WasteQueryService(BaseQueryService):
    scope = "waste"

    def search_products(self, query: str, filters: QueryFilters | None = None) -> list[SearchResult]:
        if hasattr(self._data_source, "search_products"):
            filters = filters or {}
            branch_id = filters.get("branch_id")
            search_products = self._data_source.search_products
            if "branch_id" in inspect.signature(search_products).parameters:
                return list(search_products(query, branch_id=branch_id))
            return list(search_products(query))
        return list(self.search(query, filters))

    def search_waste_records(self, query: str, filters: QueryFilters | None = None) -> list[SearchResult]:
        return list(self.search(query, filters))

    def list_for_table(self, filters: QueryFilters | None = None) -> list[TableRow]:
        if hasattr(self._data_source, "list_waste_records"):
            filters = filters or {}
            return list(self._data_source.list_waste_records(
                branch_id=filters.get("branch_id", "1"),
                period=str(filters.get("period", "Hoy")),
                search=str(filters.get("search", "")),
            ))
        return list(self.list_rows(filters))

    def get_daily_summary(self, filters: QueryFilters | None = None) -> KpiMetric:
        if hasattr(self._data_source, "get_daily_summary"):
            filters = filters or {}
            return self._data_source.get_daily_summary(branch_id=filters.get("branch_id", "1"))
        metrics = list(self.metrics(filters))
        return metrics[0] if metrics else KpiMetric("daily_waste", "Merma de hoy", {"records": 0, "loss_value": 0.0})

    def get_kpis(self, filters: QueryFilters | None = None) -> list[KpiMetric]:
        return [self.get_daily_summary(filters)]

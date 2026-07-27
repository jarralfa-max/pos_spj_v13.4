"""Read-only QueryService for the branches UI/API read models."""

from __future__ import annotations

from backend.application.queries.base_query_service import BaseQueryService, KpiMetric, QueryFilters, SearchResult, TableRow


class BranchQueryService(BaseQueryService):
    scope = "branches"

    def search_branches(self, query: str, filters: QueryFilters | None = None) -> list[SearchResult]:
        return list(self.search(query, filters))

    def list_for_table(self, filters: QueryFilters | None = None) -> list[TableRow]:
        return list(self.list_rows(filters))

    def get_kpis(self, filters: QueryFilters | None = None) -> list[KpiMetric]:
        return list(self.metrics(filters))

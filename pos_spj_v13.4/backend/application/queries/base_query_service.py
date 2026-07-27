"""Base QueryService contracts for UI reads without direct SQL in PyQt."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


QueryFilters = Mapping[str, Any]


@dataclass(frozen=True)
class SearchResult:
    """Small DTO for autocomplete/search selector results."""

    id: str
    label: str
    subtitle: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TableRow:
    """Generic read-model row for tables and dashboards."""

    id: str
    values: Mapping[str, Any]


@dataclass(frozen=True)
class KpiMetric:
    """Generic KPI read model for dashboards."""

    key: str
    label: str
    value: Any
    unit: str = ""


class QueryDataSource(Protocol):
    """Read-only data source implemented by infrastructure adapters.

    Implementations own persistence details. QueryServices expose application
    read models to UI/API code without leaking SQL or DB cursors into PyQt.
    """

    def search(self, scope: str, query: str, filters: QueryFilters | None = None) -> Sequence[SearchResult]:
        """Return autocomplete results for one query scope."""

    def list_rows(self, scope: str, filters: QueryFilters | None = None) -> Sequence[TableRow]:
        """Return table rows for one query scope."""

    def metrics(self, scope: str, filters: QueryFilters | None = None) -> Sequence[KpiMetric]:
        """Return KPI metrics for one query scope."""


class EmptyQueryDataSource:
    """Safe placeholder data source for unimplemented query adapters."""

    def search(self, scope: str, query: str, filters: QueryFilters | None = None) -> Sequence[SearchResult]:
        return []

    def list_rows(self, scope: str, filters: QueryFilters | None = None) -> Sequence[TableRow]:
        return []

    def metrics(self, scope: str, filters: QueryFilters | None = None) -> Sequence[KpiMetric]:
        return []


class BaseQueryService:
    """Base class for read-only application query services."""

    scope: str

    def __init__(self, data_source: QueryDataSource | None = None) -> None:
        self._data_source = data_source or EmptyQueryDataSource()

    def search(self, query: str, filters: QueryFilters | None = None) -> Sequence[SearchResult]:
        return self._data_source.search(self.scope, query.strip(), filters)

    def list_rows(self, filters: QueryFilters | None = None) -> Sequence[TableRow]:
        return self._data_source.list_rows(self.scope, filters)

    def metrics(self, filters: QueryFilters | None = None) -> Sequence[KpiMetric]:
        return self._data_source.metrics(self.scope, filters)

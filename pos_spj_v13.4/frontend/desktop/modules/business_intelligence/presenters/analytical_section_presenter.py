"""AnalyticalSectionPresenter (§14, BI-25) — feeds one BI section page
("Ventas"/"Inventario"/"Compras"/"Finanzas") from the REAL per-tab payload
`BiDashboardService.section_data()` already builds today (its own source
labels this "FASE 8" — the legacy `modulos/reportes_bi_v2.py` renders this
exact payload for its own tabs). This presenter, like
`ExecutiveDashboardPresenter` (BI-24), doesn't rebuild that logic — it only
translates the payload's plain "mini" dicts (title/value/unit/icon/variant;
simpler than the executive dashboard's KpiCard, no delta/semantic fields)
into the canonical `KPIDTO`/`ChartDataDTO`/table shape the new module's
Design System expects.

Only sections with a real `BiDashboardService._section_*` builder behind
them are wired through `business_intelligence_routes.py`
(ventas/inventario/compras/finanzas). "Producción"/"Precios"/"Sucursales"
have no dashboard-level aggregate query today — only per-product/per-branch
recommendation services (BI-14..17), which BI-27's unified recommendations
page surfaces instead of a fabricated aggregate here — so those three stay
placeholders (documented in `docs/refactor/BI-25_analytical_pages.md`).
"""

from __future__ import annotations

from backend.application.analytics.dto.bi_dashboard_dto import DashboardFilters
from backend.application.analytics.queries.bi_dashboard_query_service import (
    BiDashboardQueryService,
)
from backend.application.analytics.services.bi_dashboard_service import BiDashboardService
from backend.application.dto.charts.chart_data import ChartDataDTO, ChartSeriesDTO, ChartType
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.tables import ColumnSpec

_KIND_TO_CHART_TYPE = {
    "line": ChartType.LINE,
    "bar": ChartType.BAR,
    "hbar": ChartType.HORIZONTAL_BAR,
    "donut": ChartType.DONUT,
    "combo": ChartType.COMBO,
}
_VALID_VARIANTS = {"primary", "success", "danger", "warning", "info", "neutral"}


def _format_mini_value(raw: dict) -> str:
    unit = raw.get("unit", "")
    value = raw.get("value", 0) or 0
    if unit == "$":
        return f"${value:,.2f}"
    if unit == "%":
        return f"{value:.1f}%"
    if unit:
        return f"{value:,.2f}{unit}"
    return f"{value:,.0f}"


def _map_mini_kpi(index: int, raw: dict) -> KPIDTO:
    variant = raw.get("variant", "primary")
    return KPIDTO(
        key=f"kpi_{index}",
        title=raw.get("title", ""),
        value=_format_mini_value(raw),
        icon=raw.get("icon") or None,
        variant=variant if variant in _VALID_VARIANTS else "neutral",
    )


def _map_section_chart(index: int, raw: dict) -> ChartDataDTO:
    chart_type = _KIND_TO_CHART_TYPE.get(raw.get("kind"), ChartType.BAR)
    title = raw.get("title", "")
    labels = tuple(raw.get("labels") or ())
    series_raw = raw.get("series") or []
    chart_id = f"section_chart_{index}"
    if not labels or not series_raw:
        return ChartDataDTO.empty(chart_id, chart_type, title)
    series = tuple(
        ChartSeriesDTO(
            name=s.get("name", ""),
            data=tuple(float(v) if v is not None else None for v in s.get("values", ())),
        )
        for s in series_raw
    )
    return ChartDataDTO(
        chart_id=chart_id, chart_type=chart_type, title=title, subtitle=None,
        categories=labels, series=series,
    )


class SectionTableDTO:
    """Bridges one `section_data()["tables"]` entry to `StandardTable` inputs."""

    __slots__ = ("title", "columns", "rows")

    def __init__(self, title: str, columns: tuple[ColumnSpec, ...],
                 rows: tuple[tuple[str, ...], ...]) -> None:
        self.title = title
        self.columns = columns
        self.rows = rows


def _map_table(raw: dict) -> SectionTableDTO:
    columns = tuple(ColumnSpec(title=c) for c in raw.get("columns", []))
    rows = tuple(tuple("" if v is None else str(v) for v in row) for row in raw.get("rows", []))
    return SectionTableDTO(title=raw.get("title", ""), columns=columns, rows=rows)


class AnalyticalSectionPresenter:
    """Feeds one BI section page. `section_key` is `BiDashboardService`'s own
    section name ("ventas"/"inventario"/"compras"/"finanzas"), kept distinct
    from the module's `page_id` (e.g. "bi_sales") — that mapping lives in
    `business_intelligence_routes.py` so this presenter stays a pure
    translator with no navigation knowledge."""

    def __init__(self, connection, section_key: str, *, permission_checker=None) -> None:
        query_service = BiDashboardQueryService(connection)
        self._service = BiDashboardService(query_service, permission_checker=permission_checker)
        self._section_key = section_key
        self._cached: dict | None = None

    def _data(self) -> dict:
        if self._cached is None:
            self._cached = self._service.section_data(self._section_key, DashboardFilters())
        return self._cached

    def invalidate(self) -> None:
        self._cached = None

    def kpi_cards(self) -> list[KPIDTO]:
        return [_map_mini_kpi(i, k) for i, k in enumerate(self._data().get("kpis", []))]

    def charts(self) -> list[ChartDataDTO]:
        return [_map_section_chart(i, c) for i, c in enumerate(self._data().get("charts", []))]

    def tables(self) -> list[SectionTableDTO]:
        return [_map_table(t) for t in self._data().get("tables", [])]

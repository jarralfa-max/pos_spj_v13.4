"""ExecutiveDashboardPresenter (§13, BI-24) — feeds the "Resumen ejecutivo"
page's KPI bar and charts from the REAL, already-clean `BiDashboardService`
(moved to `backend/application/analytics/` in BI-4; BI-0's audit found it
has zero SQL-in-UI and a documented architecture,
`docs/architecture/BI_DASHBOARD.md` — this presenter doesn't rebuild that
service, it just bridges its pre-Design-System output shape
(`KpiCard`/`ChartData` plain dicts, §40's `bi_dashboard_dto.py`) into the
canonical `KPIDTO`/`ChartDataDTO` the new module's Design System components
expect.

Two things are deliberately dropped in that bridge, matching master-prompt
§103: `KpiCard.icon` (an emoji character in the legacy DTO) and any inline
color from `ChartData.series[].color` (canonical `ChartSeriesDTO` carries no
color at all, by design — `chart_data.py`'s own docstring: "No colors ...
those belong to the theme/renderer").
"""

from __future__ import annotations

from backend.application.analytics.dto.bi_dashboard_dto import DashboardFilters
from backend.application.analytics.queries.bi_dashboard_query_service import (
    BiDashboardQueryService,
)
from backend.application.analytics.services.bi_dashboard_service import BiDashboardService
from backend.application.dto.charts.chart_data import ChartDataDTO, ChartSeriesDTO, ChartType
from frontend.desktop.components.kpi_card import KPIDTO

_KIND_TO_CHART_TYPE = {
    "line": ChartType.LINE,
    "bar": ChartType.BAR,
    "hbar": ChartType.HORIZONTAL_BAR,
    "donut": ChartType.DONUT,
    "combo": ChartType.COMBO,
}
_SEMANTIC_TO_VARIANT = {"positive": "success", "negative": "danger", "neutral": "neutral"}
#: §13 — at most 6 primary KPIs on the executive dashboard.
_MAX_PRIMARY_KPIS = 6


def _format_kpi_value(raw: dict) -> str:
    unit = raw.get("unit", "")
    value = raw.get("value", 0) or 0
    if unit == "$":
        return f"${value:,.2f}"
    if unit == "%":
        return f"{value:.1f}%"
    if unit:
        return f"{value:,.2f}{unit}"
    return f"{value:,.0f}"


def _format_trend_value(raw: dict) -> str | None:
    delta_pct = raw.get("delta_pct")
    if delta_pct is not None:
        return f"{delta_pct:+.1f}%"
    delta_points = raw.get("delta_points")
    if delta_points is not None:
        return f"{delta_points:+.1f} pts"
    return None


def _map_kpi(raw: dict) -> KPIDTO:
    return KPIDTO(
        key=raw["key"],
        title=raw["title"],
        value=_format_kpi_value(raw),
        variant=_SEMANTIC_TO_VARIANT.get(raw.get("semantic", "neutral"), "neutral"),
        trend_value=_format_trend_value(raw),
        trend_direction=raw.get("direction"),
        tooltip=raw.get("tooltip") or None,
    )


def _map_chart(chart_key: str, raw: dict) -> ChartDataDTO:
    chart_type = _KIND_TO_CHART_TYPE.get(raw.get("kind"), ChartType.BAR)
    title = raw.get("title", "")
    labels = tuple(raw.get("labels") or ())
    series_raw = raw.get("series") or []
    if not labels or not series_raw:
        return ChartDataDTO.empty(chart_key, chart_type, title)
    series = tuple(
        ChartSeriesDTO(
            name=s.get("name", ""),
            # `None` is a legitimate gap value (e.g. the "real" series of a
            # forecast chart has no observed value yet for future dates) —
            # only cast the values that are actually present.
            data=tuple(float(v) if v is not None else None for v in s.get("values", ())),
        )
        for s in series_raw
    )
    return ChartDataDTO(
        chart_id=chart_key, chart_type=chart_type, title=title, subtitle=None,
        categories=labels, series=series,
    )


class ExecutiveDashboardPresenter:
    def __init__(self, connection, *, permission_checker=None) -> None:
        query_service = BiDashboardQueryService(connection)
        self._service = BiDashboardService(query_service, permission_checker=permission_checker)

    def kpi_cards(self) -> list[KPIDTO]:
        payload = self._service.build_dashboard(DashboardFilters())
        return [_map_kpi(k) for k in payload.kpis[:_MAX_PRIMARY_KPIS]]

    def charts(self) -> list[ChartDataDTO]:
        payload = self._service.build_dashboard(DashboardFilters())
        return [_map_chart(key, raw) for key, raw in payload.charts.items()]

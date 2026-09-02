"""OrdersAnalyticsPresenter (ORD-28) — feeds the "Análisis" page's KPI bar
and charts from ORD-27's `OrdersDeliveryAnalyticsQueryService`. Closes the
"Charts" gap ORD-27 deliberately left open (a query service alone can't
render a widget) using the SAME `HtmlChartView`/`ChartDataDTO` pipeline
`LossAnalyticsPage` already established — mirrors its shape exactly.

Decimal -> float conversion happens ONLY here, at the chart-rendering
boundary — the same "visual-only, never used for money math" exception this
codebase already grants latitude/longitude (ORD-7). `OrdersDeliveryAnalytics
QueryService` itself stays Decimal-only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from frontend.desktop.components.kpi_card import KPIDTO

from backend.application.dto.charts.chart_data import ChartDataDTO, ChartSeriesDTO, ChartType
from backend.application.orders_delivery.queries.analytics_query_service import (
    OrdersDeliveryAnalyticsQueryService,
)


class OrdersAnalyticsPresenter:
    def __init__(self, connection, *, branch_id: str, window_days: int = 30) -> None:
        self._service = OrdersDeliveryAnalyticsQueryService(connection)
        self._branch_id = branch_id
        self._window_days = window_days

    def _date_range(self) -> tuple[str, str]:
        now = datetime.now(timezone.utc)
        return (
            (now - timedelta(days=self._window_days)).isoformat(timespec="seconds"),
            now.isoformat(timespec="seconds"),
        )

    def kpi_cards(self) -> list[KPIDTO]:
        date_from, date_to = self._date_range()
        kpi = self._service.kpi_summary(branch_id=self._branch_id, date_from=date_from, date_to=date_to)
        sla = self._service.sla_breakdown(branch_id=self._branch_id, date_from=date_from, date_to=date_to)
        on_time_pct = f"{float(sla['on_time_rate']) * 100:.1f}%" if sla["on_time_rate"] is not None else "—"
        return [
            KPIDTO("orders_created", "Pedidos (30 días)", str(kpi["orders_created"])),
            KPIDTO("orders_completed", "Completados", str(kpi["orders_completed"])),
            KPIDTO("revenue", "Ingreso completado", f"${kpi['total_revenue']:,.2f}"),
            KPIDTO("on_time_rate", "Entregas a tiempo", on_time_pct,
                   variant="danger" if sla["on_time_rate"] is not None and sla["on_time_rate"] < 0.8
                   else "neutral"),
        ]

    def charts(self) -> list[ChartDataDTO]:
        date_from, date_to = self._date_range()
        drivers = self._service.driver_performance(
            branch_id=self._branch_id, date_from=date_from, date_to=date_to)
        sla = self._service.sla_breakdown(branch_id=self._branch_id, date_from=date_from, date_to=date_to)
        return [self._driver_chart(drivers), self._sla_chart(sla)]

    @staticmethod
    def _driver_chart(drivers: list[dict]) -> ChartDataDTO:
        if not drivers:
            return ChartDataDTO.empty(
                "orders_driver_performance", ChartType.BAR, "Entregas por repartidor")
        top = drivers[:10]
        categories = tuple(row["driver_id"][:8] for row in top)
        return ChartDataDTO(
            chart_id="orders_driver_performance", chart_type=ChartType.BAR,
            title="Entregas por repartidor", subtitle="Últimos 30 días",
            categories=categories,
            series=(
                ChartSeriesDTO("Completadas", tuple(float(r["deliveries_completed"]) for r in top),
                               semantic="success"),
                ChartSeriesDTO("Fallidas", tuple(float(r["deliveries_failed"]) for r in top),
                               semantic="danger"),
            ),
        )

    @staticmethod
    def _sla_chart(sla: dict) -> ChartDataDTO:
        if not sla["measurable_deliveries"]:
            return ChartDataDTO.empty(
                "orders_sla", ChartType.DONUT, "Cumplimiento de SLA",
                message="Sin entregas con ventana prometida en el período.")
        return ChartDataDTO(
            chart_id="orders_sla", chart_type=ChartType.DONUT,
            title="Cumplimiento de SLA", subtitle="Entregas con ventana prometida",
            categories=("A tiempo", "Tarde"),
            series=(ChartSeriesDTO(
                "Entregas", (float(sla["on_time_deliveries"]), float(sla["late_deliveries"]))),),
        )

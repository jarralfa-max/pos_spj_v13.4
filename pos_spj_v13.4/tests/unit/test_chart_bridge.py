from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.application.dto.charts import ChartDataDTO, ChartSeriesDTO
from frontend.desktop.charts import ChartBridge


def test_chart_bridge_renders_payload_with_template_and_renderer() -> None:
    chart = ChartDataDTO(
        chart_id="sales_daily",
        chart_type="bar",
        title="Ventas por día",
        subtitle="Últimos 7 días",
        categories=("Lunes", "Martes"),
        series=(
            ChartSeriesDTO(
                key="net_sales",
                name="Ventas netas",
                values=(Decimal("120.50"), Decimal("250.00")),
                series_type="bar",
                formatter="money",
            ),
        ),
        unit=None,
        currency_code="MXN",
        generated_at=datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc),
        freshness_state="FRESH",
        accessibility_summary="Ventas netas por día en pesos mexicanos.",
    )

    html = ChartBridge.render(chart)

    assert "window.SPJ_CHART_PAYLOAD" in html
    assert "Ventas por día" in html
    assert "echarts" in html
    assert "120.50" in html
    assert "MXN" in html

"""FASE DS-5 — chart subsystem tests (DTO, bridge, view fallback, assets)."""

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.dto.charts import (  # noqa: E402
    ChartDataDTO,
    ChartSeriesDTO,
    ChartState,
    ChartType,
)
from frontend.desktop.charts.chart_bridge import (  # noqa: E402
    build_chart_payload,
    to_json,
    to_table,
)
from frontend.desktop.themes.semantic_colors import ChartPalette  # noqa: E402

_CHARTS = Path(__file__).resolve().parents[2] / "frontend" / "desktop" / "charts"


def _sample(chart_type=ChartType.LINE) -> ChartDataDTO:
    return ChartDataDTO(
        chart_id="ventas", chart_type=chart_type, title="Ventas", subtitle="Mes",
        categories=("Lun", "Mar", "Mié"),
        series=(ChartSeriesDTO("Ventas", (10.0, 20.0, None)),
                ChartSeriesDTO("Meta", (15.0, 15.0, 15.0), semantic="warning")),
        unit="MXN", generated_at=datetime(2026, 7, 17, 12, 0))


class TestChartDataDTO:
    def test_rejects_unknown_type(self):
        with pytest.raises(ValueError):
            ChartDataDTO("x", "pyramid", "t", None, (), ())

    def test_empty_helper(self):
        dto = ChartDataDTO.empty("k", ChartType.BAR, "Título")
        assert dto.state == ChartState.EMPTY and dto.is_empty()

    def test_dto_carries_no_color_field(self):
        # the DTO/series must not expose a 'color' attribute (colors come later)
        assert not hasattr(ChartSeriesDTO("a", (1.0,)), "color")


class TestChartBridge:
    def test_palette_assigned_from_theme_not_dto(self):
        payload = build_chart_payload(_sample(), "light")
        colors = [s["color"] for s in payload["series"]]
        assert colors[0] == ChartPalette.CATEGORICAL[0]
        # semantic series maps to the status color
        assert colors[1] == ChartPalette.STATUS["warning"]

    def test_theme_affects_text_color(self):
        light = build_chart_payload(_sample(), "light")["theme"]["text"]
        dark = build_chart_payload(_sample(), "dark")["theme"]["text"]
        assert light != dark

    def test_to_json_is_valid_and_script_safe(self):
        raw = to_json(_sample(), "light")
        assert "</" not in raw  # escaped so it can't close a <script>
        data = json.loads(raw.replace("<\\/", "</"))
        assert data["chartType"] == "line"
        assert data["series"][0]["data"][2] is None

    def test_to_table_accessible_alternative(self):
        headers, rows = to_table(_sample())
        assert headers == ["Categoría", "Ventas", "Meta"]
        assert rows[0][0] == "Lun"
        assert rows[2][1] == "—"  # None → dash


class TestChartAssets:
    def test_template_and_renderer_exist(self):
        assert (_CHARTS / "templates" / "chart_base.html").exists()
        assert (_CHARTS / "renderers" / "echarts_renderer.js").exists()
        assert (_CHARTS / "vendor" / "README.md").exists()

    def test_template_uses_payload_token_and_echarts(self):
        html = (_CHARTS / "templates" / "chart_base.html").read_text(encoding="utf-8")
        assert "__CHART_PAYLOAD__" in html
        assert "echarts.min.js" in html
        assert "echarts_renderer.js" in html

    def test_renderer_reads_payload_theme_not_hardcoded_colors(self):
        js = (_CHARTS / "renderers" / "echarts_renderer.js").read_text(encoding="utf-8")
        assert "SPJChart" in js and "payload" in js
        import re
        assert not re.search(r"#[0-9A-Fa-f]{6}", js)  # colors come from payload


class TestHtmlChartView:
    def test_view_builds_and_falls_back_to_table_headless(self):
        from PyQt5.QtWidgets import QApplication

        from frontend.desktop.components.chart_view import HtmlChartView
        app = QApplication.instance() or QApplication([])  # noqa: F841
        view = HtmlChartView()
        # QtWebEngine + vendored echarts are absent in CI → tabular fallback
        assert view.uses_web_renderer() is False
        view.set_chart(_sample())  # renders the table alternative without error
        headers, rows = view.as_table_alternative(_sample())
        assert headers[0] == "Categoría"

    def test_empty_dto_shows_state(self):
        from PyQt5.QtWidgets import QApplication

        from frontend.desktop.components.chart_view import HtmlChartView
        app = QApplication.instance() or QApplication([])  # noqa: F841
        view = HtmlChartView()
        view.set_chart(ChartDataDTO.empty("k", ChartType.BAR, "Vacío"))

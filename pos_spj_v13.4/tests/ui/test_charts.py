"""FASE DS-5 — chart subsystem tests (DTO, bridge, view fallback, assets)."""

import json
import os
from dataclasses import replace
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


@pytest.fixture
def chart_theme_manager(monkeypatch):
    from frontend.desktop.themes.theme_manager import ThemeManager

    manager = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    return manager


@pytest.fixture
def recording_web_chart(monkeypatch):
    from PyQt5.QtWidgets import QWidget
    from frontend.desktop.components import chart_view

    class RecordingWebView(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.payloads = []

        def setHtml(self, html, _base_url):
            payload = html.split("window.__CHART__ = ", 1)[1]
            self.payloads.append(json.JSONDecoder().raw_decode(payload)[0])

    monkeypatch.setattr(chart_view, "QWebEngineView", RecordingWebView)
    monkeypatch.setattr(chart_view.HtmlChartView, "_can_use_web", staticmethod(lambda: True))
    return chart_view.HtmlChartView


def test_open_chart_rebuilds_html_theme_without_requerying_data(recording_web_chart, chart_theme_manager):
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance()
    view = recording_web_chart()
    view.set_chart(_sample())
    view.show()
    web = view._web
    initial = web.payloads[-1]
    assert initial["theme"]["name"] == "light"

    chart_theme_manager.set_theme("dark", app=app)

    assert len(web.payloads) == 2
    assert view._web is web
    assert web.payloads[-1]["theme"]["name"] == "dark"
    assert web.payloads[-1]["theme"]["text"] != initial["theme"]["text"]
    assert web.payloads[-1]["series"] == initial["series"]
    assert web.payloads[-1]["categories"] == initial["categories"]
    chart_theme_manager.set_theme("light", app=app)
    assert len(web.payloads) == 3
    assert web.payloads[-1] == initial
    view.close()


@pytest.mark.parametrize("state", [ChartState.LOADING, ChartState.ERROR, ChartState.OFFLINE, ChartState.EMPTY])
def test_chart_theme_change_preserves_visible_state(recording_web_chart, chart_theme_manager, state):
    from PyQt5.QtWidgets import QApplication

    view = recording_web_chart()
    view.set_chart(_sample())
    dto = ChartDataDTO.empty("k", ChartType.BAR, "Vacío") if state == ChartState.EMPTY else replace(_sample(), state=state)
    view.set_chart(dto)
    visible_state = view._stack.currentWidget()

    chart_theme_manager.set_theme("dark", app=QApplication.instance())

    assert len(view._web.payloads) == 1
    assert view._stack.currentWidget() is visible_state
    assert visible_state is view._state


def test_chart_table_fallback_keeps_selection_during_theme_change(monkeypatch, chart_theme_manager):
    from PyQt5.QtWidgets import QApplication
    from frontend.desktop.components.chart_view import HtmlChartView

    monkeypatch.setattr(HtmlChartView, "_can_use_web", staticmethod(lambda: False))
    view = HtmlChartView()
    view.set_chart(_sample())
    table = view._table
    table.setCurrentCell(1, 1)

    chart_theme_manager.set_theme("dark", app=QApplication.instance())

    assert view._table is table
    assert view._stack.currentWidget() is table
    assert (table.currentRow(), table.currentColumn()) == (1, 1)


def test_chart_theme_changes_before_first_data_and_after_deletion_are_safe(recording_web_chart, chart_theme_manager):
    from PyQt5 import sip
    from PyQt5.QtCore import QEvent
    from PyQt5.QtWidgets import QApplication

    view = recording_web_chart()
    chart_theme_manager.set_theme("dark", app=QApplication.instance())
    assert view._web.payloads == []
    view.set_chart(_sample())
    assert view._web.payloads[-1]["theme"]["name"] == "dark"
    view.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert sip.isdeleted(view)
    chart_theme_manager.set_theme("light", app=QApplication.instance())


def test_chart_theme_refresh_preserves_injected_provider_contract(recording_web_chart, chart_theme_manager):
    from PyQt5.QtWidgets import QApplication

    view = recording_web_chart(theme_provider=lambda: "light")
    view.set_chart(_sample())
    chart_theme_manager.set_theme("dark", app=QApplication.instance())
    assert len(view._web.payloads) == 2
    assert view._web.payloads[-1]["theme"]["name"] == "light"

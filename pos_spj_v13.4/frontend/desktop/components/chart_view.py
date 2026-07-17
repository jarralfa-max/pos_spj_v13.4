"""HtmlChartView (FASE DS-5) — renders a ChartDataDTO with ECharts (HTML+JS).

Pipeline: ChartDataDTO → chart_bridge → chart_base.html + echarts_renderer.js.
The view never computes metrics, runs SQL or hardcodes colors.

Graceful degradation: if QtWebEngine or the vendored ECharts asset is missing,
the view shows the accessible **tabular alternative** (the same table exposed for
screen readers), so it never renders a blank chart.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import QStackedLayout, QWidget

from backend.application.dto.charts.chart_data import ChartDataDTO, ChartState
from frontend.desktop.charts.chart_bridge import to_json, to_table
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.components.view_states import ViewState, create_state_widget
from frontend.desktop.themes.theme_manager import ThemeManager

_CHARTS_DIR = Path(__file__).resolve().parents[1] / "charts"
_TEMPLATE = _CHARTS_DIR / "templates" / "chart_base.html"
_ECHARTS = _CHARTS_DIR / "vendor" / "echarts.min.js"

try:  # QtWebEngine is present on the full desktop build, absent in headless CI
    from PyQt5.QtWebEngineWidgets import QWebEngineView  # type: ignore
    _WEB_AVAILABLE = True
except Exception:  # pragma: no cover - depends on the environment
    QWebEngineView = None  # type: ignore
    _WEB_AVAILABLE = False


class HtmlChartView(QWidget):
    def __init__(self, parent=None, *, theme_provider=None) -> None:
        super().__init__(parent)
        self.setObjectName("htmlChartView")
        self._theme_provider = theme_provider or (lambda: ThemeManager.instance().theme)
        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)

        self._web = QWebEngineView(self) if self._can_use_web() else None
        self._table = StandardTable([ColumnSpec("Categoría")], self)
        self._state = create_state_widget(ViewState.EMPTY, self)

        if self._web is not None:
            self._stack.addWidget(self._web)      # 0
        self._stack.addWidget(self._table)        # 0 or 1
        self._stack.addWidget(self._state)        # last

    @staticmethod
    def _can_use_web() -> bool:
        return _WEB_AVAILABLE and _ECHARTS.exists() and _TEMPLATE.exists()

    def uses_web_renderer(self) -> bool:
        return self._web is not None

    # public API --------------------------------------------------------------
    def set_chart(self, dto: ChartDataDTO) -> None:
        if dto.state in (ChartState.LOADING, ChartState.ERROR, ChartState.OFFLINE) \
                or dto.is_empty():
            self._show_state(dto)
            return
        if self._web is not None:
            self._render_web(dto)
        else:
            self._render_table(dto)

    # internals ---------------------------------------------------------------
    def _show_state(self, dto: ChartDataDTO) -> None:
        mapping = {
            ChartState.LOADING: ViewState.LOADING,
            ChartState.ERROR: ViewState.ERROR,
            ChartState.OFFLINE: ViewState.OFFLINE,
        }
        state = mapping.get(dto.state, ViewState.EMPTY)
        message = dto.empty_message if state == ViewState.EMPTY else None
        new_state = create_state_widget(state, self, message=message)
        self._stack.removeWidget(self._state)
        self._state.deleteLater()
        self._state = new_state
        self._stack.addWidget(self._state)
        self._stack.setCurrentWidget(self._state)

    def _render_web(self, dto: ChartDataDTO) -> None:
        html = _TEMPLATE.read_text(encoding="utf-8")
        payload = to_json(dto, self._theme_provider())
        html = html.replace("/*__CHART_PAYLOAD__*/ null", payload)
        base = QUrl.fromLocalFile(str(_TEMPLATE.parent) + "/")
        self._web.setHtml(html, base)
        self._stack.setCurrentWidget(self._web)

    def _render_table(self, dto: ChartDataDTO) -> None:
        headers, rows = to_table(dto)
        specs = [ColumnSpec(headers[0])] + [ColumnSpec(h, "numeric") for h in headers[1:]]
        # rebuild the table with the right columns
        self._stack.removeWidget(self._table)
        self._table.deleteLater()
        self._table = StandardTable(specs, self)
        self._table.load_rows(rows)
        self._stack.addWidget(self._table)
        self._stack.setCurrentWidget(self._table)

    def as_table_alternative(self, dto: ChartDataDTO):
        """Expose the accessible tabular view explicitly (for a11y toggles)."""
        return to_table(dto)

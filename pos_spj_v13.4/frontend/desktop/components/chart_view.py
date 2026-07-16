"""Canonical HTML + JavaScript chart view shell."""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget


class HtmlChartView(QWidget):
    """Chart surface for HTML/JavaScript renderers with tabular accessibility text."""

    def __init__(self, parent=None, *, accessibility_summary: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("htmlChartView")
        self.setProperty("component", "htmlChartView")
        self.setProperty("renderer", "html_js")
        self._html = ""
        self._summary = QLabel(accessibility_summary, self)
        self._summary.setObjectName("chartAccessibilitySummary")
        self._summary.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self._summary)

    def set_chart_html(self, html: str, *, accessibility_summary: str = "") -> None:
        self._html = str(html)
        if accessibility_summary:
            self._summary.setText(accessibility_summary)
            self.setAccessibleDescription(accessibility_summary)

    def chart_html(self) -> str:
        return self._html

"""Canonical dashboard grid container."""

from __future__ import annotations

from PyQt5.QtWidgets import QGridLayout, QWidget


class DashboardGrid(QWidget):
    """Responsive-ready semantic grid for dashboard cards and charts."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardGrid")
        self.setProperty("component", "dashboardGrid")
        self._layout = QGridLayout(self)

    def add_card(self, widget: QWidget, row: int, column: int, row_span: int = 1, column_span: int = 1) -> None:
        self._layout.addWidget(widget, row, column, row_span, column_span)

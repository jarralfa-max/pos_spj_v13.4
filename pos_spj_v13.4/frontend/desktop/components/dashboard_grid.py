"""DashboardGrid (FASE DS-5) — weighted dashboard layout.

Arranges a KPIBar and charts so they don't all carry the same visual weight
(e.g. a primary chart 2/3 + a secondary 1/3). Layout only — no data logic.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from frontend.desktop.themes.tokens import Spacing


class DashboardGrid(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardGrid")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(Spacing.LG)

    def add_kpi_bar(self, kpi_bar: QWidget) -> None:
        self._layout.addWidget(kpi_bar)

    def add_full_width(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def add_row(self, *widgets_with_weights: tuple[QWidget, int]) -> None:
        """Add a row of (widget, stretch) pairs. Weights control relative width."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(Spacing.LG)
        for widget, weight in widgets_with_weights:
            row.addWidget(widget, stretch=max(1, weight))
        container = QWidget(self)
        container.setLayout(row)
        self._layout.addWidget(container)

    def add_stretch(self) -> None:
        self._layout.addStretch(1)

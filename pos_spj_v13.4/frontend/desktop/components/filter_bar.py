"""Canonical filter bar container."""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

from frontend.desktop.components.buttons import StandardButton
from frontend.desktop.components.tooltip import Tooltip
from frontend.desktop.themes import DesktopSpacing


class FilterBar(QWidget):
    """Responsive-ready filter row with result count and standard clear action."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("filterBar")
        self.setProperty("component", "filterBar")
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(DesktopSpacing.SM)
        self._result_count = QLabel("", self)
        self._result_count.setObjectName("filterResultCount")
        self._clear_button: StandardButton | None = None

    def add_filter(self, widget: QWidget, *, stretch: int = 0, tooltip: str | None = None) -> None:
        if tooltip:
            Tooltip.attach(widget, title=tooltip)
        self.layout.addWidget(widget, stretch)

    def add_spacer(self) -> None:
        self.layout.addStretch(1)

    def add_result_count(self) -> None:
        self.layout.addWidget(self._result_count)

    def set_result_count(self, count: int | None, *, label: str = "resultados") -> None:
        self._result_count.setText("" if count is None else f"{count} {label}")

    def add_clear_action(self, callback, *, tooltip: str = "Limpiar filtros") -> StandardButton:
        self._clear_button = StandardButton("Limpiar", self, variant="ghost", size="sm", tooltip=tooltip)
        self._clear_button.clicked.connect(callback)
        self.layout.addWidget(self._clear_button)
        return self._clear_button

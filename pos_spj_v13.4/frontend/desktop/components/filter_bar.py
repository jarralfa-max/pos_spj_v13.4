"""Canonical filter bar container."""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QWidget

from frontend.desktop.themes import DesktopSpacing


class FilterBar(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setProperty("component", "filterBar")
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(DesktopSpacing.SM)

    def add_filter(self, widget: QWidget, *, stretch: int = 0) -> None:
        self.layout.addWidget(widget, stretch)

    def add_spacer(self) -> None:
        self.layout.addStretch(1)

"""Canonical debounced search input."""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal

from frontend.desktop.components.debounced_search_input import DebouncedSearchInput
from frontend.desktop.components.tooltip import Tooltip


class SearchInput(DebouncedSearchInput):
    """Search input that emits presenter-friendly signals without querying itself."""

    search_requested = pyqtSignal(str)
    cleared = pyqtSignal()

    def __init__(self, placeholder: str = "Buscar", debounce_ms: int = 300, parent=None) -> None:
        super().__init__(parent=parent, delay_ms=debounce_ms)
        self.setPlaceholderText(placeholder)
        self.setObjectName("searchInput")
        self.setProperty("component", "searchInput")
        Tooltip.attach(
            self,
            title="Buscar",
            description="Escribe para filtrar; presiona Enter para solicitar búsqueda.",
            shortcut="Ctrl+F",
        )
        self.returnPressed.connect(lambda: self.search_requested.emit(self.text().strip()))
        self.textChanged.connect(self._emit_cleared_when_empty)

    def _emit_cleared_when_empty(self, value: str) -> None:
        if not value:
            self.cleared.emit()

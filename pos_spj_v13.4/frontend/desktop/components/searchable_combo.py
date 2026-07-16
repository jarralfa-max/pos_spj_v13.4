"""Canonical searchable combo box for small and medium catalogs."""

from __future__ import annotations

from collections.abc import Iterable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QComboBox

from frontend.desktop.components.tooltip import Tooltip


class SearchableComboBox(QComboBox):
    """Combo box with contains-search, placeholder, and UUID item data."""

    def __init__(self, parent=None, *, placeholder: str = "Selecciona…") -> None:
        super().__init__(parent)
        self._placeholder = placeholder
        self.setObjectName("searchableComboBox")
        self.setProperty("component", "searchableComboBox")
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        completer = self.completer()
        if completer is not None:
            completer.setFilterMode(Qt.MatchContains)
        Tooltip.attach(
            self,
            title="Selector con búsqueda",
            description="Busca por texto y selecciona una opción válida del catálogo.",
        )
        self.addItem(self._placeholder, None)

    def set_options(self, options: Iterable[tuple[str, str]]) -> None:
        self.clear()
        self.addItem(self._placeholder, None)
        for item_id, label in options:
            self.addItem(str(label), str(item_id))
        self.setCurrentIndex(0)

    def selected_id(self) -> str | None:
        data = self.currentData()
        return None if data is None else str(data)

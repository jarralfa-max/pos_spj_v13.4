"""Reusable autocomplete selector for entities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget


@dataclass(frozen=True)
class SearchOption:
    id: str
    label: str
    subtitle: str = ""


SearchProvider = Callable[[str], Iterable[SearchOption]]


class SearchSelector(QWidget):
    selected = pyqtSignal(object)

    def __init__(self, parent=None, *, provider: SearchProvider | None = None, placeholder: str = "Buscar...") -> None:
        super().__init__(parent)
        self._provider = provider or (lambda _query: [])
        self._search_box = QLineEdit(self)
        self._search_box.setPlaceholderText(placeholder)
        self._results = QListWidget(self)
        self._options: list[SearchOption] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._search_box)
        layout.addWidget(self._results)

        self._search_box.textChanged.connect(self.refresh)
        self._results.itemClicked.connect(self._emit_selected)
        self._results.itemActivated.connect(self._emit_selected)

    def set_provider(self, provider: SearchProvider) -> None:
        self._provider = provider
        self.refresh(self._search_box.text())

    def refresh(self, query: str | None = None) -> None:
        query_text = self._search_box.text() if query is None else query
        self._options = list(self._provider(query_text.strip()))
        self._results.clear()
        for option in self._options:
            text = option.label if not option.subtitle else f"{option.label} — {option.subtitle}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, option)
            item.setData(32, option)  # legacy role kept for existing tests/callers
            self._results.addItem(item)

    def selected_option(self) -> SearchOption | None:
        item = self._results.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole) or item.data(32)

    def set_text_silently(self, text: str) -> None:
        self._search_box.blockSignals(True)
        self._search_box.setText(text)
        self._search_box.blockSignals(False)

    def clear_results(self) -> None:
        self._results.clear()
        self._options = []

    def clear(self) -> None:
        self._search_box.clear()
        self.clear_results()

    def _emit_selected(self, item: QListWidgetItem) -> None:
        option = item.data(Qt.UserRole) or item.data(32)
        if option is not None:
            self.selected.emit(option)

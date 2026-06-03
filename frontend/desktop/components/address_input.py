"""Address input with autocomplete provider and manual fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QCheckBox, QLineEdit, QListWidget, QListWidgetItem, QTextEdit, QVBoxLayout, QWidget


@dataclass(frozen=True)
class AddressSuggestion:
    label: str
    latitude: float | None = None
    longitude: float | None = None
    provider_payload: object | None = None


AddressProvider = Callable[[str], Iterable[AddressSuggestion]]


class AddressInput(QWidget):
    selected = pyqtSignal(object)

    def __init__(self, parent=None, *, provider: AddressProvider | None = None) -> None:
        super().__init__(parent)
        self._provider = provider or (lambda _query: [])
        self._search_box = QLineEdit(self)
        self._search_box.setPlaceholderText("Buscar dirección en mapa...")
        self._manual_toggle = QCheckBox("Captura manual", self)
        self._manual_text = QTextEdit(self)
        self._manual_text.setPlaceholderText("Escribe la dirección manualmente")
        self._suggestions = QListWidget(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._search_box)
        layout.addWidget(self._suggestions)
        layout.addWidget(self._manual_toggle)
        layout.addWidget(self._manual_text)

        self._manual_text.setVisible(False)
        self._manual_toggle.toggled.connect(self._manual_text.setVisible)
        self._search_box.textChanged.connect(self.refresh)
        self._suggestions.itemActivated.connect(self._emit_selected)

    def refresh(self, query: str) -> None:
        self._suggestions.clear()
        for suggestion in self._provider(query.strip()):
            item = QListWidgetItem(suggestion.label)
            item.setData(32, suggestion)
            self._suggestions.addItem(item)

    def value(self) -> str:
        if self._manual_toggle.isChecked():
            return self._manual_text.toPlainText().strip()
        item = self._suggestions.currentItem()
        return "" if item is None else item.text()

    def set_manual_value(self, value: str) -> None:
        self._manual_toggle.setChecked(True)
        self._manual_text.setPlainText(value.strip())

    def _emit_selected(self, item: QListWidgetItem) -> None:
        self.selected.emit(item.data(32))

"""Reusable autocomplete selector for entities."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Callable, Iterable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget


@dataclass(frozen=True)
class SearchOption:
    id: str
    label: str
    subtitle: str = ""


SearchProvider = Callable[[str], Iterable[SearchOption]]

logger = logging.getLogger("spj.search_selector")


#: Mensaje mostrado cuando el provider lanza una excepción — distinto a "sin
#: resultados" a propósito (§35 del master prompt: no presentar un fallo
#: técnico como si fueran cero coincidencias).
SEARCH_FAILED_MESSAGE = "No se pudo consultar. Intente de nuevo."
NO_RESULTS_MESSAGE = "Sin resultados."


class SearchSelector(QWidget):
    selected = pyqtSignal(object)
    #: Emitida SOLO cuando el provider lanza (no cuando simplemente no hay
    #: coincidencias). El mensaje es apto para mostrar al usuario.
    search_failed = pyqtSignal(str)

    def __init__(self, parent=None, *, provider: SearchProvider | None = None, placeholder: str = "Buscar...") -> None:
        super().__init__(parent)
        self._provider = provider or (lambda _query: [])
        self._search_box = QLineEdit(self)
        self._search_box.setPlaceholderText(placeholder)
        self._results = QListWidget(self)
        self._options: list[SearchOption] = []
        self._search_failed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._search_box)
        layout.addWidget(self._results)

        self._search_box.textChanged.connect(self.refresh)
        self._search_box.returnPressed.connect(self._emit_current_selected)
        self._results.itemClicked.connect(self._emit_selected)

    def set_provider(self, provider: SearchProvider) -> None:
        self._provider = provider
        self.refresh(self._search_box.text())

    def refresh(self, query: str | None = None) -> None:
        query_text = self._search_box.text() if query is None else query
        try:
            self._options = list(self._provider(query_text.strip()))
            self._search_failed = False
        except Exception:
            logger.exception("SearchSelector provider failed query=%r", query_text)
            self._options = []
            self._search_failed = True
        self._results.clear()
        if self._search_failed:
            self._add_status_row(SEARCH_FAILED_MESSAGE)
            self.search_failed.emit(SEARCH_FAILED_MESSAGE)
            return
        if not self._options and query_text.strip():
            self._add_status_row(NO_RESULTS_MESSAGE)
            return
        for option in self._options:
            text = option.label if not option.subtitle else f"{option.label} — {option.subtitle}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, option)
            item.setData(32, option)  # legacy role kept for existing tests/callers
            self._results.addItem(item)

    def has_search_failed(self) -> bool:
        return self._search_failed

    def _add_status_row(self, text: str) -> None:
        """A non-selectable row: distinguishes '0 matches' / 'query failed'
        from a real, pickable option without changing the selection contract."""
        item = QListWidgetItem(text)
        item.setFlags(Qt.NoItemFlags)
        item.setForeground(Qt.gray)
        self._results.addItem(item)

    def selected_option(self) -> SearchOption | None:
        item = self._results.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole) or item.data(32)

    def set_text_silently(self, text: str) -> None:
        was_blocked = self._search_box.blockSignals(True)
        try:
            self._search_box.setText(text)
        finally:
            self._search_box.blockSignals(was_blocked)

    def clear_selection(self) -> None:
        self._results.clearSelection()
        self._results.setCurrentRow(-1)

    def clear_results(self) -> None:
        self._results.clear()
        self._options = []

    def set_selected_label(self, text: str) -> None:
        self.set_text_silently(text)
        self.clear_results()

    def clear(self) -> None:
        self._search_box.clear()
        self.clear_results()

    def _emit_current_selected(self) -> None:
        item = self._results.currentItem()
        if item is not None:
            self._emit_selected(item)

    def _emit_selected(self, item: QListWidgetItem) -> None:
        option = item.data(Qt.UserRole) or item.data(32)
        if option is not None:
            self.selected.emit(option)

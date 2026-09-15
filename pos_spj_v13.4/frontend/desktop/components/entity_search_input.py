"""EntitySearchInput (FASE DS-4) — search + select for large entities by UUID.

For products, customers, suppliers, employees, lots, orders… A debounced
SearchInput drives a paginated provider (a QueryService callback returning
``SearchOption`` rows); the user selects one and the widget emits its UUID.
Never loads thousands of rows into a QComboBox.
"""

from __future__ import annotations

import logging
from typing import Callable, Iterable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from frontend.desktop.components.search_input import SearchInput
from frontend.desktop.components.search_selector import (
    NO_RESULTS_MESSAGE,
    SEARCH_FAILED_MESSAGE,
    SearchOption,
)
from frontend.desktop.themes.tokens import Spacing

logger = logging.getLogger("spj.entity_search_input")

Provider = Callable[[str], Iterable[SearchOption]]


class EntitySearchInput(QWidget):
    selected = pyqtSignal(object)   # emits the chosen entity id (UUID str)
    #: Emitida SOLO cuando el provider lanza (no cuando simplemente no hay
    #: coincidencias). El mensaje es apto para mostrar al usuario.
    search_failed = pyqtSignal(str)

    def __init__(self, parent=None, *, provider: Provider | None = None,
                 placeholder: str = "Buscar por nombre, código o teléfono",
                 max_results: int = 25, debounce_ms: int = 300) -> None:
        super().__init__(parent)
        self.setObjectName("entitySearchInput")
        self._provider = provider or (lambda _q: [])
        self._max_results = max_results
        self._selected_id = None
        self._selected_label = ""
        self._search_failed = False

        self._search = SearchInput(self, placeholder=placeholder, debounce_ms=debounce_ms)
        self._results = QListWidget(self)
        self._results.setObjectName("entitySearchResults")
        self._results.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.XXS)
        layout.addWidget(self._search)
        layout.addWidget(self._results)

        self._search.search_changed.connect(self._run_search)
        self._results.itemClicked.connect(self._choose)

    def set_provider(self, provider: Provider) -> None:
        self._provider = provider

    def selected_id(self):
        return self._selected_id

    def selected_label(self) -> str:
        return self._selected_label

    def set_selected_label(self, entity_id, label: str) -> None:
        self._selected_id = entity_id
        self._selected_label = str(label or "")
        self._search.blockSignals(True)
        self._search.setText(label)
        self._search.blockSignals(False)
        self._results.setVisible(False)

    def clear(self) -> None:
        self._selected_id = None
        self._selected_label = ""
        self._search.clear()
        self._results.clear()
        self._results.setVisible(False)

    def has_search_failed(self) -> bool:
        return self._search_failed

    def _run_search(self, query: str) -> None:
        self._results.clear()
        if not query:
            self._results.setVisible(False)
            self._search_failed = False
            return
        try:
            options = list(self._provider(query))[: self._max_results]
            self._search_failed = False
        except Exception:
            logger.exception("EntitySearchInput provider failed query=%r", query)
            options = []
            self._search_failed = True
        if self._search_failed:
            self._add_status_row(SEARCH_FAILED_MESSAGE)
            self._results.setVisible(True)
            self.search_failed.emit(SEARCH_FAILED_MESSAGE)
            return
        if not options:
            self._add_status_row(NO_RESULTS_MESSAGE)
            self._results.setVisible(True)
            return
        for option in options:
            text = option.label if not option.subtitle else f"{option.label} — {option.subtitle}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, option)
            self._results.addItem(item)
        self._results.setVisible(bool(options))

    def _add_status_row(self, text: str) -> None:
        """A non-selectable row: distinguishes '0 matches' / 'query failed'
        from a real, pickable option without changing the selection contract."""
        item = QListWidgetItem(text)
        item.setFlags(Qt.NoItemFlags)
        item.setForeground(Qt.gray)
        self._results.addItem(item)

    def _choose(self, item: QListWidgetItem) -> None:
        option: SearchOption = item.data(Qt.UserRole)
        if option is None:
            return
        self._selected_id = option.id
        self._selected_label = option.label
        self._search.blockSignals(True)
        self._search.setText(option.label)
        self._search.blockSignals(False)
        self._results.setVisible(False)
        self.selected.emit(option.id)

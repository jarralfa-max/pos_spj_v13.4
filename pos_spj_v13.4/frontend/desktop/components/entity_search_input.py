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
from frontend.desktop.components.search_selector import SearchOption
from frontend.desktop.themes.tokens import Spacing

logger = logging.getLogger("spj.entity_search_input")

Provider = Callable[[str], Iterable[SearchOption]]


class EntitySearchInput(QWidget):
    selected = pyqtSignal(object)   # emits the chosen entity id (UUID str)

    def __init__(self, parent=None, *, provider: Provider | None = None,
                 placeholder: str = "Buscar por nombre, código o teléfono",
                 max_results: int = 25, debounce_ms: int = 300) -> None:
        super().__init__(parent)
        self.setObjectName("entitySearchInput")
        self._provider = provider or (lambda _q: [])
        self._max_results = max_results
        self._selected_id = None

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

    def set_selected_label(self, entity_id, label: str) -> None:
        self._selected_id = entity_id
        self._search.blockSignals(True)
        self._search.setText(label)
        self._search.blockSignals(False)
        self._results.setVisible(False)

    def clear(self) -> None:
        self._selected_id = None
        self._search.clear()
        self._results.clear()
        self._results.setVisible(False)

    def _run_search(self, query: str) -> None:
        self._results.clear()
        if not query:
            self._results.setVisible(False)
            return
        try:
            options = list(self._provider(query))[: self._max_results]
        except Exception:
            logger.exception("EntitySearchInput provider failed query=%r", query)
            options = []
        for option in options:
            text = option.label if not option.subtitle else f"{option.label} — {option.subtitle}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, option)
            self._results.addItem(item)
        self._results.setVisible(bool(options))

    def _choose(self, item: QListWidgetItem) -> None:
        option: SearchOption = item.data(Qt.UserRole)
        if option is None:
            return
        self._selected_id = option.id
        self._search.blockSignals(True)
        self._search.setText(option.label)
        self._search.blockSignals(False)
        self._results.setVisible(False)
        self.selected.emit(option.id)

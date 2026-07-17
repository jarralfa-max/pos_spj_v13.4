"""SearchableComboBox (FASE DS-4) — small/medium catalogs with type-to-filter.

For roles, branches, categories, units, statuses. IDs live in item data; the box
never inserts arbitrary text and never shows a false default (starts on
"Selecciona…").
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QComboBox

from frontend.desktop.i18n.es_mx import ui

_PLACEHOLDER_ID = None


class SearchableComboBox(QComboBox):
    selection_changed = pyqtSignal(object)  # emits the current id (or None)

    def __init__(self, parent=None, *, placeholder: str | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("searchableCombo")
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        completer = self.completer()
        if completer is not None:
            completer.setFilterMode(Qt.MatchContains)
            completer.setCompletionMode(completer.PopupCompletion)
        self._placeholder = placeholder or ui("select.placeholder")
        self.addItem(self._placeholder, _PLACEHOLDER_ID)
        self.currentIndexChanged.connect(
            lambda _i: self.selection_changed.emit(self.current_id()))

    def set_options(self, options: list[tuple], *, keep_selection: bool = False) -> None:
        current = self.current_id() if keep_selection else _PLACEHOLDER_ID
        self.blockSignals(True)
        self.clear()
        self.addItem(self._placeholder, _PLACEHOLDER_ID)
        for value, label in options:
            self.addItem(str(label), value)
        self.blockSignals(False)
        if keep_selection and current is not _PLACEHOLDER_ID:
            self.set_current_id(current)

    def current_id(self):
        return self.currentData()

    def set_current_id(self, value) -> bool:
        index = self.findData(value)
        if index < 0:
            return False
        self.setCurrentIndex(index)
        return True

    def has_selection(self) -> bool:
        return self.current_id() is not _PLACEHOLDER_ID

"""SearchInput (FASE DS-4) — debounced search field. Emits signals; never queries.

The widget does no SQL/queries: it debounces text and emits ``search_changed``
(and ``search_submitted`` on Enter). Escape clears; the field is focusable via a
keyboard shortcut wired by the host page.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QLineEdit

from frontend.desktop.components.icons import Icons
from frontend.desktop.components.tooltip import apply_tooltip


class SearchInput(QLineEdit):
    search_changed = pyqtSignal(str)
    search_submitted = pyqtSignal(str)

    def __init__(self, parent=None, *, placeholder: str = "Buscar…",
                 debounce_ms: int = 300) -> None:
        super().__init__(parent)
        self.setObjectName("searchInput")
        self.setClearButtonEnabled(True)
        self.setPlaceholderText(placeholder)
        self.setProperty("icon", Icons.SEARCH)
        apply_tooltip(self, "Buscar", shortcut="Ctrl+F")

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(0, debounce_ms))
        self._timer.timeout.connect(lambda: self.search_changed.emit(self.text().strip()))
        self.textChanged.connect(lambda _t: self._timer.start())
        self.returnPressed.connect(lambda: self.search_submitted.emit(self.text().strip()))

    def keyPressEvent(self, event):  # noqa: N802 (Qt override)
        if event.key() == Qt.Key_Escape and self.text():
            self.clear()
            self.search_changed.emit("")
            return
        super().keyPressEvent(event)

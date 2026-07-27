"""Theme-neutral debounced search input."""

from __future__ import annotations

from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtWidgets import QLineEdit


class DebouncedSearchInput(QLineEdit):
    """QLineEdit that emits searchChanged after the user stops typing."""

    searchChanged = pyqtSignal(str)

    def __init__(self, parent=None, *, delay_ms: int = 350) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self._emit_search)
        self.textChanged.connect(lambda _text: self._timer.start())
        self.setClearButtonEnabled(True)

    def _emit_search(self) -> None:
        self.searchChanged.emit(self.text().strip())

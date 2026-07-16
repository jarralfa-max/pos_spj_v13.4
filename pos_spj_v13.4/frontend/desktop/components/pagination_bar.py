"""Reusable desktop pagination bar."""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

from frontend.desktop.components.buttons import StandardButton
from frontend.desktop.themes import DesktopSpacing


class PaginationBar(QWidget):
    """Offset pagination widget for QueryService-backed tables."""

    pageChanged = pyqtSignal(int, int)

    def __init__(self, parent=None, *, page_size: int = 25) -> None:
        super().__init__(parent)
        self.setObjectName("paginationBar")
        self.setProperty("component", "paginationBar")
        self._page_size = page_size
        self._offset = 0
        self._has_next = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(DesktopSpacing.SM)
        self._previous = StandardButton("Anterior", self, variant="secondary", size="sm", tooltip="Mostrar la página anterior")
        self._next = StandardButton("Siguiente", self, variant="secondary", size="sm", tooltip="Mostrar la página siguiente")
        self._label = QLabel("Página 1", self)
        self._label.setObjectName("paginationLabel")
        self._label.setAccessibleName("Página actual")
        self._previous.clicked.connect(self.previous_page)
        self._next.clicked.connect(self.next_page)
        layout.addStretch(1)
        layout.addWidget(self._previous)
        layout.addWidget(self._label)
        layout.addWidget(self._next)
        self.update_state(total_rows=0)

    @property
    def limit(self) -> int:
        return self._page_size

    @property
    def offset(self) -> int:
        return self._offset

    def reset(self) -> None:
        self._offset = 0
        self.update_state(total_rows=0)

    def update_state(self, *, total_rows: int) -> None:
        self._has_next = total_rows >= self._page_size
        page = (self._offset // self._page_size) + 1
        self._label.setText(f"Página {page}")
        self._previous.setEnabled(self._offset > 0)
        self._next.setEnabled(self._has_next)

    def previous_page(self) -> None:
        if self._offset == 0:
            return
        self._offset = max(0, self._offset - self._page_size)
        self.pageChanged.emit(self._page_size, self._offset)

    def next_page(self) -> None:
        if not self._has_next:
            return
        self._offset += self._page_size
        self.pageChanged.emit(self._page_size, self._offset)

"""Small status badge widget with theme-provided semantic styling."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel


class StatusBadge(QLabel):
    """Semantic status badge; colors are supplied by the active desktop theme."""

    def __init__(self, text: str = "Pendiente", parent=None, *, status: str = "neutral") -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.set_status(status)

    def set_status(self, status: str) -> None:
        self.setProperty("status", status)
        self.setProperty("component", "statusBadge")
        self.style().unpolish(self)
        self.style().polish(self)

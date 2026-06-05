"""Small status badge widget with standard semantic colors."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel


_STATUS_COLORS = {
    "success": ("#E8F5E9", "#1B5E20"),
    "warning": ("#FFF8E1", "#E65100"),
    "danger": ("#FFEBEE", "#B71C1C"),
    "info": ("#E3F2FD", "#0D47A1"),
    "neutral": ("#ECEFF1", "#263238"),
}


class StatusBadge(QLabel):
    def __init__(self, text: str = "Pendiente", parent=None, *, status: str = "neutral") -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.set_status(status)

    def set_status(self, status: str) -> None:
        background, foreground = _STATUS_COLORS.get(status, _STATUS_COLORS["neutral"])
        self.setProperty("status", status)
        self.setStyleSheet(
            f"background-color: {background}; color: {foreground}; border-radius: 8px; padding: 2px 8px;"
        )

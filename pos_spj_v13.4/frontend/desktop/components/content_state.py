"""Canonical content-ready state marker."""

from __future__ import annotations

from PyQt5.QtWidgets import QWidget


class ContentState(QWidget):
    """Semantic wrapper for ready content when a page uses state stacks."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("contentState")
        self.setProperty("state", "READY")

"""Canonical HR dialog shell for leave_request."""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QVBoxLayout

from frontend.desktop.themes import DesktopSpacing


class HRLeaveRequestDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG)

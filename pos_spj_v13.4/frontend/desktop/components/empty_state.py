"""Theme-neutral empty state component."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.themes import DesktopSpacing


class EmptyState(QWidget):
    """Reusable empty state that avoids local color/style declarations."""

    def __init__(self, title: str, description: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("emptyState")
        self.setProperty("state", "EMPTY")
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG)
        layout.setSpacing(DesktopSpacing.SM)
        self._title = QLabel(title, self)
        self._title.setAlignment(Qt.AlignCenter)
        self._description = QLabel(description, self)
        self._description.setAlignment(Qt.AlignCenter)
        self._description.setWordWrap(True)
        layout.addWidget(self._title)
        layout.addWidget(self._description)

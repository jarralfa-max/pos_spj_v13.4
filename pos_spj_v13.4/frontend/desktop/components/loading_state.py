"""Theme-neutral loading state component."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel


class LoadingState(QLabel):
    """Small reusable label for predictable loading feedback."""

    def __init__(self, text: str = "Cargando información...", parent=None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setVisible(False)

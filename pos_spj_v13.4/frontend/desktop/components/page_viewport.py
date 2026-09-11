"""Canonical overflow boundary between a page and its available workspace."""

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import QFrame, QScrollArea, QSizePolicy, QWidget


class PageViewport(QScrollArea):
    """Expand normal content and scroll content whose minimum size cannot fit."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("pageViewport")
        self.setProperty("overflowPolicy", "auto")
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAccessibleName("Contenido desplazable")

    def minimumSizeHint(self) -> QSize:
        # A large form must enlarge its scrollable content, never the shell.
        return QSize(0, 0)

    def set_page(self, page: QWidget) -> None:
        self.setWidget(page)

    def page(self) -> QWidget | None:
        return self.widget()

    def viewport_size(self) -> QSize:
        return self.viewport().size()

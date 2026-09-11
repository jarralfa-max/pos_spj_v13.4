"""Canonical top-level geometry and branding for desktop windows."""
from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QApplication, QMainWindow

from frontend.desktop.components.branding import BrandAssetProvider


class StandardWindow(QMainWindow):
    def __init__(self, parent=None, *, title: str = "JUANIS · SPJ ERP / POS") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowIcon(BrandAssetProvider.window_icon())
        self.setMinimumSize(640, 480)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(QSize(1440, 900).boundedTo(available.size()))
        else:
            self.resize(1280, 720)

    def showEvent(self, event) -> None:  # noqa: N802
        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            self.setMinimumSize(self.minimumSize().boundedTo(available.size()))
            self.resize(self.size().boundedTo(available.size()))
        super().showEvent(event)

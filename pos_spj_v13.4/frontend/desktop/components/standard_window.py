"""Canonical top-level geometry and branding for desktop windows."""
from PyQt5.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow

from frontend.desktop.components.branding import BrandAssetProvider


class StandardWindow(QMainWindow):
    _DEFAULT_MINIMUM = QSize(640, 480)
    _DEFAULT_SIZE = QSize(1440, 900)

    def __init__(self, parent=None, *, title: str = "JUANIS · SPJ ERP / POS") -> None:
        super().__init__(parent)
        self._desktop_screen = None
        self._desktop_handle = None
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(1)
        self._fit_timer.timeout.connect(self._fit_available_area)
        self.setWindowTitle(title)
        self.setWindowIcon(BrandAssetProvider.window_icon())
        self.setMinimumSize(self._DEFAULT_MINIMUM)
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.setMinimumSize(self._DEFAULT_MINIMUM.boundedTo(available.size()))
            self.resize(self._DEFAULT_SIZE.boundedTo(available.size()))
        else:
            self.resize(1280, 720)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        handle = self.windowHandle()
        if handle is not self._desktop_handle:
            if self._desktop_handle is not None:
                try:
                    self._desktop_handle.screenChanged.disconnect(self._screen_changed)
                except (RuntimeError, TypeError):
                    pass
            self._desktop_handle = handle
            if handle is not None:
                handle.screenChanged.connect(self._screen_changed)
        self._screen_changed()

    def _screen_changed(self, _screen=None) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not self._desktop_screen:
            if self._desktop_screen is not None:
                try:
                    self._desktop_screen.availableGeometryChanged.disconnect(self._schedule_fit)
                except (RuntimeError, TypeError):
                    pass
            self._desktop_screen = screen
            if screen is not None:
                screen.availableGeometryChanged.connect(self._schedule_fit)
        self._schedule_fit()

    def _schedule_fit(self, _geometry=None) -> None:
        self._fit_available_area()
        # Native decorations and restored geometry settle after the Qt event.
        self._fit_timer.start()

    def _fit_available_area(self, _geometry=None) -> None:
        screen = self._desktop_screen
        if screen is None:
            return
        available = screen.availableGeometry()
        if not available.isValid():
            return
        frame = self.frameGeometry()
        # Screen bounds include the native titlebar and window borders.
        extra = QSize(max(0, frame.width() - self.width()),
                      max(0, frame.height() - self.height()))
        limit = (available.size() - extra).expandedTo(QSize(1, 1))
        self.setMinimumSize(self._DEFAULT_MINIMUM.boundedTo(limit))
        if self.windowState() & (Qt.WindowMaximized | Qt.WindowFullScreen | Qt.WindowMinimized):
            return  # Qt owns geometry while the window is in a managed state.
        size = self.size().boundedTo(limit)
        frame_size = size + extra
        x = max(available.left(), min(frame.left(), available.right() - frame_size.width() + 1))
        y = max(available.top(), min(frame.top(), available.bottom() - frame_size.height() + 1))
        inset = self.geometry().topLeft() - frame.topLeft()
        self.setGeometry(QRect(QPoint(x, y) + inset, size))

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self._schedule_fit()

    def _check_frame(self) -> None:
        # The platform can deliver its final move/resize after a state change.
        # Recheck that event instead of assuming one timer settles every WM.
        if (self._desktop_screen is not None and self.isVisible() and
                not self.windowState() & (Qt.WindowMaximized | Qt.WindowFullScreen | Qt.WindowMinimized) and
                not self._desktop_screen.availableGeometry().contains(self.frameGeometry())):
            self._fit_timer.start()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._check_frame()

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        self._check_frame()

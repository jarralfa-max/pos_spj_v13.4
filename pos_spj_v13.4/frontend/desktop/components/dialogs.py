"""Canonical dialogs (FASE DS-3).

StandardDialog + confirmation/destructive/form variants. Spanish buttons, viewport-
safe sizing, initial focus, Escape when safe, theme-aware via `#standardDialog`.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtCore import QRect, QSize, Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLayout,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components.branding import BrandAssetProvider
from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.i18n.es_mx import ui
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import DialogMetrics, Spacing, density_metrics


class StandardDialog(QDialog):
    """Base dialog: title + content area + a standard button box."""

    def __init__(self, parent=None, *, title: str = "",
                 width: int = DialogMetrics.WIDTH_SM) -> None:
        super().__init__(parent)
        self.setObjectName("standardDialog")
        self.setWindowTitle(title)
        self.setWindowIcon(BrandAssetProvider.window_icon())
        self.setProperty("overflowPolicy", "auto")
        self._preferred_width = width
        self._screen = None
        self._window_handle = None
        self._fitting = False
        self._shown_once = False
        self._requested_minimum = QSize(0, 0)
        self._bounded_minimum = None
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.setInterval(1)
        self._fit_timer.timeout.connect(self.fit_to_viewport)
        self._frame = QVBoxLayout(self)
        self._frame.setSizeConstraint(QLayout.SetNoConstraint)
        self._frame.setContentsMargins(DialogMetrics.PADDING, DialogMetrics.PADDING,
                                      DialogMetrics.PADDING, DialogMetrics.PADDING)
        self._frame.setSpacing(Spacing.MD)
        self._heading = QLabel(title, self)
        self._heading.setProperty("role", "dialogTitle")
        self._heading.setWordWrap(True)
        self._heading.setVisible(bool(title))
        self._frame.addWidget(self._heading)
        self.windowTitleChanged.connect(self._update_heading)
        self.viewport = PageViewport(self)
        self._body = QWidget()
        # Keep the established _root contract used by existing dialog subclasses.
        self._root = QVBoxLayout(self._body)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(Spacing.MD)
        self.viewport.set_page(self._body)
        self._frame.addWidget(self.viewport, 1)
        self._button_boxes = []
        ThemeManager.instance().density_changed.connect(self._density_changed)

    def content_layout(self) -> QVBoxLayout:
        return self._root

    def add_button_box(self, *, ok_text: str = None, cancel_text: str = None,
                       ok_role=QDialogButtonBox.Ok,
                       on_accept: Callable[[], None] | None = None) -> QDialogButtonBox:
        """Add a sticky footer; a validation callback owns acceptance when given."""
        box = QDialogButtonBox(ok_role | QDialogButtonBox.Cancel, self)
        box.button(ok_role).setText(ok_text or ui("action.accept"))
        box.button(QDialogButtonBox.Cancel).setText(cancel_text or ui("action.cancel"))
        box.button(ok_role).setDefault(True)
        box.accepted.connect(self.accept if on_accept is None else on_accept)
        box.rejected.connect(self.reject)
        self._frame.addWidget(box)
        self._button_boxes.append(box)
        self._density_changed()
        return box

    def _update_heading(self, title: str) -> None:
        self._heading.setText(title)
        self._heading.setVisible(bool(title))

    def _density_changed(self, _density=None):
        for box in self._button_boxes:
            for button in box.buttons():
                button.setMinimumHeight(density_metrics().button_height)
                button.setAccessibleName(button.text())
        if self.isVisible():
            self._fit_timer.start()

    def available_geometry(self):
        parent = self.parentWidget()
        # Before Qt creates the native dialog, use its owner's monitor. Once
        # it has a handle, follow the dialog itself when it is moved elsewhere.
        screen = (self.screen() if self.windowHandle() is not None or parent is None
                  else parent.screen())
        screen = screen or QApplication.primaryScreen()
        return screen.availableGeometry() if screen is not None else QRect()

    def _schedule_fit(self, _geometry=None) -> None:
        self.fit_to_viewport()
        self._fit_timer.start()

    def fit_to_viewport(self):
        """Clamp the full native frame to the available monitor work area."""
        if self._fitting:
            return
        self._fitting = True
        try:
            available = self.available_geometry()
            if not available.isValid():
                return
            frame = self.frameGeometry()
            extra = (frame.size() - self.size()).expandedTo(QSize(0, 0))
            maximum = QSize(max(1, available.width() - extra.width()),
                            max(1, available.height() - extra.height()))
            minimum = self.minimumSize()
            if self._bounded_minimum is None or minimum != self._bounded_minimum:
                self._requested_minimum = minimum
            self.setMaximumSize(maximum)
            self._bounded_minimum = self._requested_minimum.boundedTo(maximum)
            self.setMinimumSize(self._bounded_minimum)
            self.resize(self.size().boundedTo(maximum))
            frame = self.frameGeometry()
            x = max(available.left(), min(frame.left(), available.right() - frame.width() + 1))
            y = max(available.top(), min(frame.top(), available.bottom() - frame.height() + 1))
            self.move(x, y)
        finally:
            self._fitting = False

    def showEvent(self, event):
        super().showEvent(event)
        handle = self.windowHandle()
        if handle is not self._window_handle:
            if self._window_handle is not None:
                try:
                    self._window_handle.screenChanged.disconnect(self._screen_changed)
                except (RuntimeError, TypeError):
                    pass
            self._window_handle = handle
            if handle is not None:
                handle.screenChanged.connect(self._screen_changed)
        self._screen_changed()
        available = self.available_geometry()
        if not self._shown_once and available.isValid():
            self.resize(min(self._preferred_width, available.width()),
                        min(max(self.sizeHint().height(), self._body.sizeHint().height() + self._frame.spacing() * 4), available.height()))
        self._shown_once = True
        self._schedule_fit()

    def _screen_changed(self, _screen=None):
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not self._screen:
            if self._screen is not None:
                try:
                    self._screen.availableGeometryChanged.disconnect(self._schedule_fit)
                except (RuntimeError, TypeError):
                    pass
            self._screen = screen
            if screen is not None:
                screen.availableGeometryChanged.connect(self._schedule_fit)
        self._schedule_fit()

    def moveEvent(self, event):
        super().moveEvent(event)
        if (self._fitting or not self.isVisible() or
                self.windowState() & (Qt.WindowMaximized | Qt.WindowFullScreen | Qt.WindowMinimized)):
            return
        available = self.available_geometry()
        frame = self.frameGeometry()
        if not available.isValid() or available.contains(frame):
            return
        if (frame.width() <= available.width() and frame.height() <= available.height() and
                any(screen is not self._screen and screen.availableGeometry().intersects(frame)
                    for screen in QApplication.screens())):
            return  # Allow intermediate positions while crossing to another screen.
        self._fit_timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible():
            self.fit_to_viewport()


class ConfirmationDialog(StandardDialog):
    def __init__(self, parent=None, *, title: str = "", message: str = "",
                 confirm_text: str | None = None) -> None:
        super().__init__(parent, title=title)
        label = QLabel(message, self)
        label.setWordWrap(True)
        self._root.addWidget(label)
        box = self.add_button_box(ok_text=confirm_text or ui("action.confirm"))
        box.button(QDialogButtonBox.Ok).setDefault(True)


class DestructiveConfirmationDialog(StandardDialog):
    """Confirmation for irreversible actions; the confirm button is danger-styled."""

    def __init__(self, parent=None, *, title: str = "", message: str = "",
                 confirm_text: str | None = None) -> None:
        super().__init__(parent, title=title)
        label = QLabel(message, self)
        label.setWordWrap(True)
        self._root.addWidget(label)
        box = self.add_button_box(ok_text=confirm_text or ui("action.delete"))
        ok = box.button(QDialogButtonBox.Ok)
        ok.setProperty("variant", "danger")
        ok.setObjectName("standardButton")
        ok.setDefault(False)
        box.button(QDialogButtonBox.Cancel).setDefault(True)
        box.button(QDialogButtonBox.Cancel).setFocus()


class FormDialog(StandardDialog):
    """A dialog wrapping a QFormLayout; subclasses fill ``self.form``."""

    def __init__(self, parent=None, *, title: str = "",
                 width: int = DialogMetrics.WIDTH_MD) -> None:
        super().__init__(parent, title=title, width=width)
        self.form = QFormLayout()
        self.form.setSpacing(Spacing.SM)
        self._root.addLayout(self.form)

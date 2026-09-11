"""Canonical dialogs (FASE DS-3).

StandardDialog + confirmation/destructive/form variants. Spanish buttons, viewport-
safe sizing, initial focus, Escape when safe, theme-aware via `#standardDialog`.
"""

from __future__ import annotations

from PyQt5.QtCore import QEvent, QSize, QTimer
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
        self._frame = QVBoxLayout(self)
        self._frame.setSizeConstraint(QLayout.SetNoConstraint)
        self._frame.setContentsMargins(DialogMetrics.PADDING, DialogMetrics.PADDING,
                                      DialogMetrics.PADDING, DialogMetrics.PADDING)
        self._frame.setSpacing(Spacing.MD)
        if title:
            heading = QLabel(title, self)
            heading.setProperty("role", "dialogTitle")
            heading.setWordWrap(True)
            self._frame.addWidget(heading)
        self.viewport = PageViewport(self)
        self._body = QWidget()
        # Keep the established _root contract used by existing dialog subclasses.
        self._root = QVBoxLayout(self._body)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(Spacing.MD)
        self.viewport.set_page(self._body)
        self._frame.addWidget(self.viewport, 1)
        self._button_boxes = []
        self._screen = None
        self._fitting = False
        ThemeManager.instance().density_changed.connect(self._density_changed)

    def content_layout(self) -> QVBoxLayout:
        return self._root

    def add_button_box(self, *, ok_text: str = None, cancel_text: str = None,
                       ok_role=QDialogButtonBox.Ok) -> QDialogButtonBox:
        box = QDialogButtonBox(ok_role | QDialogButtonBox.Cancel, self)
        box.button(ok_role).setText(ok_text or ui("action.accept"))
        box.button(QDialogButtonBox.Cancel).setText(cancel_text or ui("action.cancel"))
        box.button(ok_role).setDefault(True)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        self._frame.addWidget(box)
        self._button_boxes.append(box)
        self._density_changed()
        return box

    def _density_changed(self, _density=None):
        for box in self._button_boxes:
            for button in box.buttons():
                button.setMinimumHeight(density_metrics().button_height)
                button.setAccessibleName(button.text())
        if self.isVisible():
            QTimer.singleShot(0, self.fit_to_viewport)

    def available_geometry(self):
        parent = self.parentWidget()
        screen = parent.screen() if parent is not None else self.screen()
        return (screen or QApplication.primaryScreen()).availableGeometry()

    def fit_to_viewport(self):
        """Clamp the full native frame to the available monitor work area."""
        if self._fitting:
            return
        self._fitting = True
        try:
            available = self.available_geometry()
            frame = self.frameGeometry()
            extra = frame.size() - self.size()
            maximum = QSize(max(1, available.width() - extra.width()),
                            max(1, available.height() - extra.height()))
            self.setMaximumSize(maximum)
            self.resize(self.size().boundedTo(maximum))
            frame = self.frameGeometry()
            x = max(available.left(), min(frame.left(), available.right() - frame.width() + 1))
            y = max(available.top(), min(frame.top(), available.bottom() - frame.height() + 1))
            self.move(x, y)
        finally:
            self._fitting = False

    def showEvent(self, event):
        super().showEvent(event)
        if self._screen is None and self.windowHandle() is not None:
            self.windowHandle().screenChanged.connect(self._screen_changed)
            self._screen_changed(self.screen())
        available = self.available_geometry()
        self.resize(min(self._preferred_width, available.width()),
                    min(max(self.sizeHint().height(), self._body.sizeHint().height() + self._frame.spacing() * 4), available.height()))
        self.fit_to_viewport()
        QTimer.singleShot(0, self.fit_to_viewport)

    def _screen_changed(self, screen):
        if self._screen is not None:
            self._screen.availableGeometryChanged.disconnect(self.fit_to_viewport)
        self._screen = screen
        if screen is not None:
            screen.availableGeometryChanged.connect(self.fit_to_viewport)
        self.fit_to_viewport()

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

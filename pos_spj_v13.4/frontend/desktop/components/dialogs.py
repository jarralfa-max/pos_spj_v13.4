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
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components.branding import BrandAssetProvider
from frontend.desktop.components.icons import IconProvider, Icons
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
        self._footer_widgets = []
        ThemeManager.instance().density_changed.connect(self._density_changed)

    def content_layout(self) -> QVBoxLayout:
        return self._root

    def add_footer_widget(self, widget: QWidget) -> QWidget:
        """Keep existing module actions outside the scroll without rewiring them."""
        if widget not in self._footer_widgets:
            self._frame.addWidget(widget)
            self._footer_widgets.append(widget)
            if isinstance(widget, QDialogButtonBox):
                self._button_boxes.append(widget)
            self._density_changed()
        return widget

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
        self.add_footer_widget(box)
        return box

    def _update_heading(self, title: str) -> None:
        self._heading.setText(title)
        self._heading.setVisible(bool(title))

    def _density_changed(self, _density=None):
        for widget in self._footer_widgets:
            buttons = ([widget] if isinstance(widget, QPushButton)
                       else widget.findChildren(QPushButton))
            for button in buttons:
                button.setMinimumHeight(density_metrics().button_height)
                if not button.accessibleName():
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

    @staticmethod
    def get_text(parent, title: str, label: str, *, text: str = "") -> tuple[str, bool]:
        """Capture text with the shared shell; the caller keeps its validation."""
        from frontend.desktop.components.text_inputs import StandardLineEdit

        dialog = FormDialog(parent, title=title)
        field = StandardLineEdit(dialog)
        field.setText(text)
        field.setAccessibleName(label)
        dialog.form.addRow(label, field)
        dialog.add_button_box()
        field.setFocus()
        try:
            accepted = dialog.exec_() == QDialog.Accepted
            return (field.text() if accepted else "", accepted)
        finally:
            dialog.deleteLater()

    @staticmethod
    def get_item(parent, title: str, label: str, items, current: int = 0,
                 editable: bool = False) -> tuple[str, bool]:
        """Select from a short catalog without bypassing the dialog policy."""
        from frontend.desktop.components.selection_controls import StandardComboBox

        dialog = FormDialog(parent, title=title)
        field = StandardComboBox(dialog)
        field.addItems(items)
        field.setEditable(editable)
        field.setCurrentIndex(current)
        field.setAccessibleName(label)
        dialog.form.addRow(label, field)
        dialog.add_button_box()
        field.setFocus()
        try:
            accepted = dialog.exec_() == QDialog.Accepted
            return (field.currentText() if accepted else "", accepted)
        finally:
            dialog.deleteLater()


# Qt order used to lay out and auto-detect message buttons.
_MESSAGE_BUTTONS = (
    (QMessageBox.Ok, "Aceptar"), (QMessageBox.Save, "Guardar"),
    (QMessageBox.SaveAll, "Guardar todo"), (QMessageBox.Open, "Abrir"),
    (QMessageBox.Yes, "Sí"), (QMessageBox.YesToAll, "Sí a todo"),
    (QMessageBox.No, "No"), (QMessageBox.NoToAll, "No a todo"),
    (QMessageBox.Abort, "Abortar"), (QMessageBox.Retry, "Reintentar"),
    (QMessageBox.Ignore, "Ignorar"), (QMessageBox.Close, "Cerrar"),
    (QMessageBox.Cancel, "Cancelar"), (QMessageBox.Discard, "Descartar"),
    (QMessageBox.Help, "Ayuda"), (QMessageBox.Apply, "Aplicar"),
    (QMessageBox.Reset, "Restablecer"), (QMessageBox.RestoreDefaults, "Restaurar valores"),
)
_ACCEPT_ROLES = (QDialogButtonBox.AcceptRole, QDialogButtonBox.YesRole)
# level -> (icon, icon state, accessible level name)
_MESSAGE_LEVELS = {
    "information": (Icons.INFO, "info", "Información"),
    "question": (Icons.INFO, "info", "Confirmación"),
    "warning": (Icons.WARNING, "warning", "Advertencia"),
    "critical": (Icons.ERROR, "danger", "Error"),
}


class MessageDialog(StandardDialog):
    """Canonical message box: the StandardDialog shell with QMessageBox's API.

    The static methods keep QMessageBox's signature, return values and
    constants, so callers compare against ``MessageDialog.Yes`` exactly as they
    compared against ``QMessageBox.Yes``. Buttons are Spanish, the message is
    plain text and the level is carried by icon and accessible name, not only
    color. Default/Escape buttons follow QMessageBox's role-based detection.
    """

    StandardButton = QMessageBox.StandardButton
    NoButton = QMessageBox.NoButton
    Ok, Cancel, Close = QMessageBox.Ok, QMessageBox.Cancel, QMessageBox.Close
    Yes, No = QMessageBox.Yes, QMessageBox.No
    YesToAll, NoToAll = QMessageBox.YesToAll, QMessageBox.NoToAll
    Save, SaveAll, Open, Discard = QMessageBox.Save, QMessageBox.SaveAll, QMessageBox.Open, QMessageBox.Discard
    Abort, Retry, Ignore, Apply = QMessageBox.Abort, QMessageBox.Retry, QMessageBox.Ignore, QMessageBox.Apply
    Help, Reset, RestoreDefaults = QMessageBox.Help, QMessageBox.Reset, QMessageBox.RestoreDefaults
    ButtonRole = QMessageBox.ButtonRole
    AcceptRole, RejectRole, DestructiveRole = QMessageBox.AcceptRole, QMessageBox.RejectRole, QMessageBox.DestructiveRole
    ActionRole, YesRole, NoRole = QMessageBox.ActionRole, QMessageBox.YesRole, QMessageBox.NoRole

    def __init__(self, parent=None, *, level: str = "information", title: str = "",
                 text: str = "", buttons=QMessageBox.Ok,
                 default_button=QMessageBox.NoButton) -> None:
        if level not in _MESSAGE_LEVELS:
            raise ValueError(f"Nivel de mensaje no reconocido: {level}")
        super().__init__(parent, title=title)
        icon_name, icon_state, level_name = _MESSAGE_LEVELS[level]
        self.setProperty("messageLevel", level)
        self.setAccessibleName(f"{level_name}: {title}" if title else level_name)
        self.setAccessibleDescription(text)

        self._icon = QLabel(self)
        self._icon.setObjectName("messageDialogIcon")
        self._icon.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        IconProvider.bind(self._icon, icon_name, size=32, state=icon_state)
        self._icon.setAccessibleName(level_name)
        self._text = QLabel(text, self)
        self._text.setObjectName("messageDialogText")
        self._text.setTextFormat(Qt.PlainText)
        self._text.setWordWrap(True)
        self._text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._text.setAccessibleName(text)
        row = QHBoxLayout()
        row.setSpacing(Spacing.MD)
        row.addWidget(self._icon, 0, Qt.AlignTop)
        row.addWidget(self._text, 1)
        self._root.addLayout(row)

        self._box = QDialogButtonBox(self)
        self._box.clicked.connect(self._on_clicked)
        self._clicked: QPushButton | None = None
        self._escape: QPushButton | None = None
        for standard, label in _MESSAGE_BUTTONS:
            if int(buttons) & int(standard):
                self._box.addButton(QDialogButtonBox.StandardButton(int(standard))).setText(label)
        self.add_footer_widget(self._box)
        self._apply_default(default_button)

    # ── QMessageBox-compatible instance API ────────────────────────────────
    def addButton(self, text: str, role) -> QPushButton:  # noqa: N802 - Qt API
        button = self._box.addButton(text, QDialogButtonBox.ButtonRole(int(role)))
        self._density_changed()
        self._apply_default(QMessageBox.NoButton)
        return button

    def clickedButton(self) -> QPushButton | None:  # noqa: N802 - Qt API
        return self._clicked

    def standardButton(self, button) -> "QMessageBox.StandardButton":  # noqa: N802
        if button is None:
            return QMessageBox.NoButton
        return QMessageBox.StandardButton(int(self._box.standardButton(button)))

    def text(self) -> str:
        return self._text.text()

    # ── QMessageBox-compatible static API ──────────────────────────────────
    @classmethod
    def information(cls, parent, title, text, buttons=QMessageBox.Ok,
                    defaultButton=QMessageBox.NoButton):  # noqa: N803 - Qt API
        return cls._show("information", parent, title, text, buttons, defaultButton)

    @classmethod
    def warning(cls, parent, title, text, buttons=QMessageBox.Ok,
                defaultButton=QMessageBox.NoButton):  # noqa: N803 - Qt API
        return cls._show("warning", parent, title, text, buttons, defaultButton)

    @classmethod
    def critical(cls, parent, title, text, buttons=QMessageBox.Ok,
                 defaultButton=QMessageBox.NoButton):  # noqa: N803 - Qt API
        return cls._show("critical", parent, title, text, buttons, defaultButton)

    @classmethod
    def question(cls, parent, title, text, buttons=QMessageBox.Yes | QMessageBox.No,
                 defaultButton=QMessageBox.NoButton):  # noqa: N803 - Qt API
        return cls._show("question", parent, title, text, buttons, defaultButton)

    @classmethod
    def _show(cls, level, parent, title, text, buttons, default_button):
        dialog = cls(parent, level=level, title=title, text=str(text),
                     buttons=buttons, default_button=default_button)
        try:
            dialog.exec_()
            return dialog.standardButton(dialog.clickedButton())
        finally:
            dialog.deleteLater()

    # ── behavior ───────────────────────────────────────────────────────────
    def _apply_default(self, default_button) -> None:
        buttons = self._box.buttons()
        target = self._box.button(QDialogButtonBox.StandardButton(int(default_button))) \
            if int(default_button) else None
        if target is None:
            # Qt focuses the first auto-default button of the Windows layout: YesRole, then AcceptRole.
            target = next((b for role in (QDialogButtonBox.YesRole, QDialogButtonBox.AcceptRole)
                           for b in buttons if self._box.buttonRole(b) == role), None)
        for button in buttons:
            button.setDefault(button is target)
        if target is not None:
            target.setFocus()
        # QMessageBox: a lone button, else the reject-role one, else a single no-role one.
        rejects = [b for b in buttons if self._box.buttonRole(b) == QDialogButtonBox.RejectRole]
        nos = [b for b in buttons if self._box.buttonRole(b) == QDialogButtonBox.NoRole]
        self._escape = (buttons[0] if len(buttons) == 1 else rejects[0] if rejects
                        else nos[0] if len(nos) == 1 else None)

    def _on_clicked(self, button) -> None:
        self._clicked = button
        role = self._box.buttonRole(button)
        self.done(QDialog.Accepted if role in _ACCEPT_ROLES else QDialog.Rejected)

    # Escape and the window's close button resolve to the escape button, or do
    # nothing without one, as in QMessageBox. A programmatic reject() still closes.
    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key_Escape and event.modifiers() == Qt.NoModifier:
            if self._escape is not None:
                self._escape.click()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._clicked is None:
            if self._escape is None:
                event.ignore()
                return
            self._clicked = self._escape
        super().closeEvent(event)

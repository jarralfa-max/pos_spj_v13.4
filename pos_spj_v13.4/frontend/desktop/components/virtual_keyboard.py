"""Reusable virtual-keyboard affordance for touch-friendly desktop inputs."""

from __future__ import annotations

import os
import sys

from PyQt5.QtCore import QEvent, QObject, QSettings, Qt
from PyQt5.QtWidgets import QAbstractSpinBox, QAction, QGridLayout, QLineEdit, QPushButton

from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.icons import IconProvider, Icons
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics

INPUT_MODES = ("text", "integer", "decimal", "money", "weight", "phone", "email")
KEYBOARD_MODES = ("auto_open", "icon_only", "disabled")
_NUMERIC_MODES = ("integer", "decimal", "money", "weight")


class VirtualKeyboard(StandardDialog):
    """Shared touch keyboard; edits the target through its existing validator."""

    def __init__(self, target: QLineEdit, *, input_mode: str = "text") -> None:
        super().__init__(target.window(), title="Teclado", width=640)
        self.setWindowFlags(Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setModal(False)
        self.setObjectName("virtualKeyboard")
        self.target = target
        self.input_mode = input_mode
        self._uppercase = False
        target.destroyed.connect(self.close)
        if input_mode in _NUMERIC_MODES or input_mode == "phone":
            rows = [list("123"), list("456"), list("789"), ["0"]]
            if input_mode in ("decimal", "money", "weight"):
                rows[-1].append(".")
            elif input_mode == "phone":
                rows[-1].append("+")
        else:
            rows = [list("1234567890"), list("qwertyuiop"), list("asdfghjklñ"), list("zxcvbnm")]
            rows[3].append("Mayús")
            rows.append(["@", ".", "-", "_"] if input_mode == "email" else ["Espacio", ".", ",", "-"])
        grid = QGridLayout()
        self._root.addLayout(grid)
        self.keys = {}
        for row, labels in enumerate(rows):
            column = 0
            for label in labels:
                button = create_secondary_button(self, label)
                button.setFocusPolicy(Qt.NoFocus)
                button.setMinimumSize(density_metrics("touch").icon_button_size,
                                      density_metrics("touch").button_height)
                button.clicked.connect(lambda _checked=False, value=label: self.press_key(value))
                span = 3 if label == "Espacio" else 2 if label == "Mayús" else 1
                grid.addWidget(button, row, column, 1, span)
                column += span
                self.keys[label] = button
        erase = create_secondary_button(self, "Borrar")
        erase.setFocusPolicy(Qt.NoFocus)
        erase.setMinimumHeight(density_metrics("touch").button_height)
        erase.clicked.connect(self.backspace)
        grid.addWidget(erase, len(rows), 0, 1, max(len(row) for row in rows))
        close = create_secondary_button(self, "Cerrar teclado")
        close.setFocusPolicy(Qt.NoFocus)
        close.setMinimumHeight(density_metrics("touch").button_height)
        close.clicked.connect(self.hide)
        self._frame.addWidget(close)
        # Connect after the buttons' global density handlers, so the keyboard
        # remains a touch surface even on a compact desktop workstation.
        ThemeManager.instance().density_changed.connect(self._keep_touch_targets)
        self._keep_touch_targets()

    def _keep_touch_targets(self, _density=None):
        metrics = density_metrics("touch")
        for button in self.findChildren(QPushButton):
            button.setMinimumSize(metrics.icon_button_size, metrics.button_height)

    def showEvent(self, event):
        # Fit the full key grid when the monitor allows it. A text keyboard
        # needs more width than a numeric keypad at the same touch density.
        self.ensurePolished()
        self._preferred_width = max(self._preferred_width, self.sizeHint().width())
        super().showEvent(event)

    def insert_text(self, text: str):
        if self.target.isEnabled() and not self.target.isReadOnly():
            self.target.insert(text)

    def press_key(self, value: str):
        if value == "Mayús":
            self._uppercase = not self._uppercase
            for label, button in self.keys.items():
                if len(label) == 1 and label.isalpha():
                    button.setText(label.upper() if self._uppercase else label)
            self.keys["Mayús"].setText("Minús" if self._uppercase else "Mayús")
        else:
            self.insert_text(" " if value == "Espacio" else value.upper() if self._uppercase else value)

    def backspace(self):
        if self.target.isEnabled() and not self.target.isReadOnly():
            self.target.backspace()


class KeyboardAwareInput(QObject):
    """Equip an existing specialized input without replacing its validation.

    Auto-open responds only to an explicit pointer interaction. Tab focus,
    scanner key streams, scale updates and normal hardware typing never open it.
    """

    def __init__(self, target: QLineEdit, *, input_mode="text", mode=None,
                 terminal_key="default", settings=None, hardware_source="") -> None:
        super().__init__(target)
        if input_mode not in INPUT_MODES:
            raise ValueError(f"Unsupported input mode: {input_mode}")
        self.target = target
        self.input_mode = input_mode
        self.hardware_source = hardware_source
        self._settings = settings if settings is not None else QSettings("JUANIS", "SPJ")
        self._settings_key = f"keyboard/{terminal_key}/mode"
        stored = self._settings.value(self._settings_key, "icon_only")
        self.mode = "icon_only"
        self.keyboard = None
        self.action = QAction(target)
        self.action.setObjectName("virtualKeyboardAction")
        icon_name = Icons.NUMERIC_KEYPAD if input_mode in _NUMERIC_MODES else Icons.KEYBOARD
        IconProvider.bind(self.action, icon_name)
        label = "Mostrar teclado numérico" if input_mode in _NUMERIC_MODES else "Mostrar teclado"
        self.action.setToolTip(label)
        self.action.setText(label)
        self.action.triggered.connect(self.open)
        target.addAction(self.action, QLineEdit.TrailingPosition)
        target.setProperty("virtualKeyboard", "numeric" if input_mode in _NUMERIC_MODES else "text")
        target.setProperty("keyboardInputMode", input_mode)
        target.installEventFilter(self)
        self.set_mode(mode if mode is not None else stored, persist=False)
        ThemeManager.instance().density_changed.connect(self._density_changed)
        self._density_changed()

    def _density_changed(self, _density=None):
        parent = self.target.parentWidget()
        control = parent if isinstance(parent, QAbstractSpinBox) else self.target
        control.setMinimumHeight(density_metrics().input_height)

    def set_mode(self, mode: str, *, persist=True):
        if mode not in KEYBOARD_MODES:
            raise ValueError(f"Unsupported keyboard mode: {mode}")
        self.mode = mode
        self.action.setVisible(mode != "disabled" and not self.hardware_source)
        self.target.setProperty("keyboardMode", mode)
        if mode == "disabled" and self.keyboard is not None:
            self.keyboard.hide()
        if persist:
            self._settings.setValue(self._settings_key, mode)

    def open(self):
        if (self.mode == "disabled" or self.hardware_source or
                self.target.property("hardwareInput") in ("scanner", "scale", "keyboard") or
                not self.target.isEnabled() or self.target.isReadOnly()):
            return
        if self.keyboard is None:
            self.keyboard = VirtualKeyboard(self.target, input_mode=self.input_mode)
        self.keyboard.show()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonRelease and self.mode == "auto_open":
            self.open()
        elif event.type() == QEvent.FocusOut and self.keyboard is not None:
            self.keyboard.hide()
        return False


def open_virtual_keyboard(*, numeric: bool = False) -> bool:
    """Open the platform keyboard/keypad when the OS exposes one.

    The component is deliberately best-effort: UI workflows must remain usable
    with a physical keyboard and must never fail because the OSK is unavailable.
    """

    if sys.platform.startswith("win"):
        command = "osk.exe"
        if numeric:
            command = os.environ.get("SPJ_NUMERIC_KEYPAD_COMMAND", command)
        try:
            return bool(os.spawnlp(os.P_NOWAIT, command, command))
        except OSError:
            return False
    return False


def attach_virtual_keyboard_action(line_edit: QLineEdit, *, numeric: bool = False,
                                  input_mode: str | None = None) -> QAction:
    """Attach a trailing action to a QLineEdit without duplicating OSK logic."""

    controller = getattr(line_edit, "_keyboard_controller", None)
    if controller is not None and controller.action in line_edit.actions():
        return controller.action
    if controller is not None:
        line_edit.removeEventFilter(controller)
        controller.deleteLater()
    if input_mode is None:
        control = line_edit.parentWidget() if isinstance(line_edit.parentWidget(), QAbstractSpinBox) else line_edit
        name = type(control).__name__.lower()
        input_mode = next((mode for mode in ("phone", "email", "money", "weight", "integer") if mode in name),
                          "decimal" if numeric else "text")
    controller = KeyboardAwareInput(line_edit, input_mode=input_mode)
    line_edit._keyboard_controller = controller
    line_edit.setAccessibleName(line_edit.accessibleName() or line_edit.placeholderText())
    return controller.action

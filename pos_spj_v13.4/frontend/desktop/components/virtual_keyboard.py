"""Reusable virtual-keyboard affordance for touch-friendly desktop inputs."""

from __future__ import annotations

import os
import sys

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QLineEdit

from frontend.desktop.components.icons import Icons


def open_virtual_keyboard(*, numeric: bool = False) -> bool:
    """Open the platform keyboard/keypad when the OS exposes one.

    The component is deliberately best-effort: UI workflows must remain usable
    with a physical keyboard and must never fail because the OSK is unavailable.
    """

    if sys.platform.startswith("win"):
        command = "osk.exe"
        if numeric:
            command = os.environ.get("SPJ_NUMERIC_KEYPAD_COMMAND", command)
        return bool(os.spawnlp(os.P_NOWAIT, command, command))
    return False


def attach_virtual_keyboard_action(line_edit: QLineEdit, *, numeric: bool = False) -> QAction:
    """Attach a trailing action to a QLineEdit without duplicating OSK logic."""

    action = QAction(line_edit)
    action.setObjectName("virtualKeyboardAction")
    action.setProperty("icon", Icons.NUMERIC_KEYPAD if numeric else Icons.KEYBOARD)
    action.setIcon(QIcon.fromTheme("accessories-calculator" if numeric else "input-keyboard"))
    action.setToolTip("Mostrar teclado numerico" if numeric else "Mostrar teclado")
    action.setText("Mostrar teclado numerico" if numeric else "Mostrar teclado")
    action.triggered.connect(lambda: open_virtual_keyboard(numeric=numeric))
    line_edit.addAction(action, QLineEdit.TrailingPosition)
    line_edit.setAccessibleName(line_edit.accessibleName() or line_edit.placeholderText())
    line_edit.setProperty("virtualKeyboard", "numeric" if numeric else "text")
    return action

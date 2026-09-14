"""Integer input component for whole-number capture."""

from __future__ import annotations

from PyQt5.QtWidgets import QSpinBox

from frontend.desktop.components.virtual_keyboard import attach_virtual_keyboard_action
from frontend.desktop.themes.theme_manager import bind_input_density


class IntegerInput(QSpinBox):
    def __init__(self, parent=None, *, minimum: int = 0, maximum: int = 999999999) -> None:
        super().__init__(parent)
        self.setRange(minimum, maximum)
        self.setValue(0)
        self.setKeyboardTracking(False)
        bind_input_density(self)
        attach_virtual_keyboard_action(self.lineEdit(), numeric=True)

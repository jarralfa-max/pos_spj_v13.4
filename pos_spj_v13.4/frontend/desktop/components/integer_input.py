"""Integer input component for whole-number capture."""

from __future__ import annotations

from PyQt5.QtWidgets import QSpinBox


class IntegerInput(QSpinBox):
    def __init__(self, parent=None, *, minimum: int = 0, maximum: int = 999999999) -> None:
        super().__init__(parent)
        self.setRange(minimum, maximum)
        self.setValue(0)
        self.setKeyboardTracking(False)

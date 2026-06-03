"""WhatsApp/E.164 phone capture component."""

from __future__ import annotations

import re

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLineEdit, QWidget


E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class PhoneInput(QWidget):
    value_changed = pyqtSignal(str)

    def __init__(self, parent=None, *, placeholder: str = "+5215512345678") -> None:
        super().__init__(parent)
        self._input = QLineEdit(self)
        self._input.setPlaceholderText(placeholder)
        self._input.textChanged.connect(self._handle_text_changed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._input)

    def value(self) -> str:
        return self._input.text().strip()

    def set_value(self, value: str) -> None:
        self._input.setText(value.strip())

    def is_valid(self) -> bool:
        return bool(E164_RE.fullmatch(self.value()))

    def _handle_text_changed(self, raw_value: str) -> None:
        self.value_changed.emit(raw_value.strip())

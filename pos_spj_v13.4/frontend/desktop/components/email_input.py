"""EmailInput (FASE DS-4) — email capture with sync validation + safe normalization.

Normalizes only what is safe (trim + lowercase the domain) — never rewrites the
local part arbitrarily. Exposes verified/unverified as display state.
"""

from __future__ import annotations

import re

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QLineEdit

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailInput(QLineEdit):
    value_changed = pyqtSignal()

    def __init__(self, parent=None, *, required: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("emailInput")
        self._required = required
        self.setPlaceholderText("nombre@dominio.com")
        self.textChanged.connect(lambda _t: self.value_changed.emit())

    def email(self) -> str:
        """Return the normalized email (trimmed; domain lowercased)."""
        text = self.text().strip()
        if "@" not in text:
            return text
        local, _, domain = text.rpartition("@")
        return f"{local}@{domain.lower()}"

    def set_email(self, value: str | None) -> None:
        self.setText((value or "").strip())

    def is_valid(self) -> bool:
        text = self.text().strip()
        if not text:
            return not self._required
        return bool(_EMAIL_RE.match(text))

    def error_message(self) -> str | None:
        if self.is_valid():
            return None
        if not self.text().strip():
            return "El correo es obligatorio."
        return "El correo no tiene un formato válido."

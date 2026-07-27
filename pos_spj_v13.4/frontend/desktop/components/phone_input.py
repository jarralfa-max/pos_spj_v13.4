"""Deprecated phone component wrapper.

PhoneWidget is the official SPJ phone input. This wrapper exists only so older
imports keep working while code migrates to `modulos.spj_phone_widget.PhoneWidget`.
"""
from __future__ import annotations

from modulos.spj_phone_widget import PhoneWidget


class PhoneInput(PhoneWidget):
    def __init__(self, parent=None, *, placeholder: str = "+5215512345678") -> None:
        del placeholder
        super().__init__(parent=parent)

    def value(self) -> str:
        return self.get_e164()

    def set_value(self, value: str) -> None:
        self.set_phone(value)

    def is_valid(self) -> bool:
        return bool(self.value().startswith("+") and 8 <= len(self.value()) <= 16)

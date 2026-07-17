"""TaxIdentifierInput (FASE DS-4) — RFC / CURP / VAT / generic tax id.

Normalizes to uppercase and strips outer spaces, validates the pattern for the
selected kind, and distinguishes persona física vs moral for RFC. It never
claims real fiscal validation (that requires an authorized service).
"""

from __future__ import annotations

import re

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QLineEdit

# RFC: 3-4 letters + 6 digits (YYMMDD) + 3 homoclave chars.
_RFC_RE = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")
_RFC_MORAL_LETTERS = 3   # persona moral: 3 letters
_RFC_FISICA_LETTERS = 4  # persona física: 4 letters
_CURP_RE = re.compile(r"^[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d$")
_VAT_RE = re.compile(r"^[A-Z0-9]{8,14}$")


class TaxIdentifierInput(QLineEdit):
    value_changed = pyqtSignal()

    KIND_RFC = "RFC"
    KIND_CURP = "CURP"
    KIND_VAT = "VAT"
    KIND_CUSTOM = "CUSTOM"

    def __init__(self, parent=None, *, kind: str = KIND_RFC, required: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("taxIdentifierInput")
        self._kind = kind
        self._required = required
        self.setPlaceholderText(kind)
        self.setMaxLength(20)
        self.textChanged.connect(lambda _t: self.value_changed.emit())

    def value(self) -> str:
        """Normalized identifier (uppercase, no outer spaces)."""
        return self.text().strip().upper()

    def set_value(self, value: str | None) -> None:
        self.setText((value or "").strip().upper())

    def rfc_person_type(self) -> str | None:
        """For RFC: 'moral' (3 letters) or 'fisica' (4 letters); else None."""
        if self._kind != self.KIND_RFC or not self.is_valid():
            return None
        letters = len(re.match(r"^[A-ZÑ&]+", self.value()).group(0))
        if letters == _RFC_MORAL_LETTERS:
            return "moral"
        if letters == _RFC_FISICA_LETTERS:
            return "fisica"
        return None

    def is_valid(self) -> bool:
        text = self.value()
        if not text:
            return not self._required
        if self._kind == self.KIND_RFC:
            return bool(_RFC_RE.match(text))
        if self._kind == self.KIND_CURP:
            return bool(_CURP_RE.match(text))
        if self._kind == self.KIND_VAT:
            return bool(_VAT_RE.match(text))
        return True  # CUSTOM: only presence checked above

    def error_message(self) -> str | None:
        if self.is_valid():
            return None
        if not self.value():
            return f"El {self._kind} es obligatorio."
        return f"El {self._kind} no tiene un formato válido."

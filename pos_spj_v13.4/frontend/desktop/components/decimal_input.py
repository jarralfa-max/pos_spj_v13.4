"""DecimalInput (FASE DS-4) — exact decimal capture.

Backed by a QLineEdit and parsed straight to ``Decimal`` so the domain value is
never a float. Supports precision, min/max and a nullable (empty) state that is
distinct from zero.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QLineEdit


class DecimalInput(QLineEdit):
    value_changed = pyqtSignal()

    def __init__(self, parent=None, *, precision: int = 2,
                 minimum: Decimal | str | None = None,
                 maximum: Decimal | str | None = None,
                 nullable: bool = False, suffix: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("decimalInput")
        self._precision = max(0, precision)
        self._min = Decimal(str(minimum)) if minimum is not None else None
        self._max = Decimal(str(maximum)) if maximum is not None else None
        self._nullable = nullable
        self._suffix = suffix
        self.setPlaceholderText("0" if not nullable else "")
        if suffix:
            # suffix is display-only context, shown as a companion, not stored
            self.setToolTip(f"Valor en {suffix.strip()}")
        self.textChanged.connect(lambda _t: self.value_changed.emit())

    # value -------------------------------------------------------------------
    def decimal_value(self) -> Decimal | None:
        text = self.text().strip().replace(",", "")
        if not text:
            return None if self._nullable else Decimal(0)
        try:
            return Decimal(text).quantize(self._quant())
        except InvalidOperation:
            return None

    def set_decimal(self, value: Decimal | str | int | None) -> None:
        if value is None or value == "":
            self.setText("")
            return
        try:
            self.setText(f"{Decimal(str(value)).quantize(self._quant())}")
        except InvalidOperation:
            self.setText("")

    # validation --------------------------------------------------------------
    def is_valid(self) -> bool:
        text = self.text().strip().replace(",", "")
        if not text:
            return self._nullable
        try:
            value = Decimal(text)
        except InvalidOperation:
            return False
        if self._min is not None and value < self._min:
            return False
        if self._max is not None and value > self._max:
            return False
        return True

    def error_message(self) -> str | None:
        if self.is_valid():
            return None
        if not self.text().strip():
            return "Este campo es obligatorio."
        if self.decimal_value() is None:
            return "Ingresa un número válido."
        if self._min is not None and (self.decimal_value() or Decimal(0)) < self._min:
            return f"El valor mínimo es {self._min}."
        if self._max is not None and (self.decimal_value() or Decimal(0)) > self._max:
            return f"El valor máximo es {self._max}."
        return "Valor inválido."

    def _quant(self) -> Decimal:
        return Decimal(1).scaleb(-self._precision) if self._precision else Decimal(1)

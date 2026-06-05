"""Standard numeric input components for the desktop UI."""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QDoubleSpinBox


class NumericInput(QDoubleSpinBox):
    """Base numeric input that starts at zero and centralizes formatting."""

    def __init__(self, parent=None, *, decimals: int = 2, minimum: float = 0.0, maximum: float = 999999999.0) -> None:
        super().__init__(parent)
        self.setDecimals(decimals)
        self.setRange(minimum, maximum)
        self.setValue(0)
        self.setKeyboardTracking(False)

    def decimal_value(self) -> Decimal:
        return Decimal(str(self.value()))

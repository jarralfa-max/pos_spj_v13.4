"""Canonical decimal input for enterprise desktop forms."""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QDoubleSpinBox

from frontend.desktop.components.tooltip import Tooltip


class DecimalInput(QDoubleSpinBox):
    """Decimal numeric input that exposes Decimal values to callers."""

    def __init__(
        self,
        parent=None,
        *,
        minimum: Decimal | int | str = Decimal("0"),
        maximum: Decimal | int | str = Decimal("999999999"),
        decimals: int = 3,
        step: Decimal | int | str = Decimal("0.001"),
        nullable: bool = False,
    ) -> None:
        super().__init__(parent)
        self._nullable = nullable
        self.setObjectName("decimalInput")
        self.setProperty("component", "decimalInput")
        self.setDecimals(decimals)
        self.setRange(float(Decimal(str(minimum))), float(Decimal(str(maximum))))
        self.setSingleStep(float(Decimal(str(step))))
        self.setKeyboardTracking(False)
        Tooltip.attach(
            self,
            title="Número decimal",
            description="Captura cantidades con precisión decimal; el dominio recibe Decimal.",
        )

    def decimal_value(self) -> Decimal:
        return Decimal(str(self.value()))

    def set_decimal_value(self, value: Decimal | int | str) -> None:
        self.setValue(float(Decimal(str(value))))

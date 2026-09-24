"""Standard numeric input components for the desktop UI."""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QDoubleSpinBox

from frontend.desktop.components.virtual_keyboard import attach_virtual_keyboard_action
from frontend.desktop.themes.theme_manager import bind_input_density


class NumericInput(QDoubleSpinBox):
    """Base numeric input that starts at zero and centralizes formatting."""

    def __init__(self, parent=None, *, decimals: int = 2, minimum: float = 0.0, maximum: float = 999999999.0) -> None:
        super().__init__(parent)
        self.setDecimals(decimals)
        self.setRange(minimum, maximum)
        self.setValue(0)
        self.setKeyboardTracking(False)
        bind_input_density(self)
        attach_virtual_keyboard_action(self.lineEdit(), numeric=True)

    def decimal_value(self) -> Decimal:
        return Decimal(str(self.value()))

    def set_decimal_value(self, value: Decimal | str | None) -> None:
        """Precarga el campo para EDITAR un valor existente.

        El `float` intermedio no introduce una imprecisión nueva: `QDoubleSpinBox`
        ya guarda el número como `float` y `decimal_value()` existe justo para
        convertirlo de vuelta al leerlo. Lo que no debe hacerse es aritmética de
        dinero sobre esto — para eso está `Money`, que rechaza `float` por diseño.

        `None` deja el campo en cero, que es el estado inicial de todo campo
        numérico de captura.
        """
        if value is None or value == "":
            self.setValue(0)
            return
        try:
            self.setValue(float(Decimal(str(value))))
        except (ArithmeticError, ValueError):
            self.setValue(0)

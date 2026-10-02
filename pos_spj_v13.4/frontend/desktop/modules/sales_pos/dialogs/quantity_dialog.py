"""QuantityDialog — corregir la cantidad de una línea por pieza (§12).

Las líneas por peso usan `WeightCaptureDialog`. Aquí sólo se captura el
número; si es válido lo decide el caso de uso (`UpdateSaleLineQuantityUseCase`
→ `QuantityPolicy`), y su motivo se muestra si lo rechaza.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components import FormField, QuantityInput, StandardDialog, StandardForm


class QuantityDialog(StandardDialog):
    def __init__(self, *, product_name: str, unit: str, current: Decimal, parent=None) -> None:
        super().__init__(parent, title=f"Cantidad — {product_name}")
        self.setObjectName("posQuantityDialog")
        self.quantity: Decimal | None = None

        form = StandardForm(self)
        self._quantity = QuantityInput(self, decimals=0)
        self._quantity.set_decimal_value(current)
        form.add_field("quantity", FormField(f"Cantidad ({unit})", self._quantity, required=True))
        self.content_layout().addWidget(form)

        self._error = QLabel("", self)
        self._error.setProperty("state", "error")
        self._error.hide()
        self.content_layout().addWidget(self._error)

        box = self.add_button_box(ok_text="Actualizar")
        box.accepted.disconnect()
        box.accepted.connect(self._submit)
        self._quantity.setFocus()
        self._quantity.selectAll()

    def set_quantity(self, value: Decimal) -> None:
        self._quantity.set_decimal_value(value)

    def _submit(self) -> None:
        value = self._quantity.decimal_value()
        if value <= 0:
            self._error.setText("La cantidad debe ser mayor a cero. Para quitar la línea usa "
                                "«Quitar».")
            self._error.show()
            return
        self.quantity = value.quantize(Decimal("1"))
        self.accept()

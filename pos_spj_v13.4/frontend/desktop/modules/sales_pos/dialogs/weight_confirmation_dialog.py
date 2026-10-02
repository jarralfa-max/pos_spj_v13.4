"""WeightCaptureDialog — el peso de un producto que se vende por peso (§18-19).

Re-auditoría POS (2026-10-01), medido en la base real: los 11 productos se
venden por KG y el POS agregaba "1" al hacer clic, sin preguntar el peso ni
dejar corregirlo. Este diálogo captura el peso en kilogramos (con gramos) y lo
valida el DOMINIO (`WeightPolicy`, vía el presentador) — aquí no se decide si
un peso es válido.

Báscula: no hay ningún controlador de báscula conectado en este repositorio ni
dispositivo de báscula dado de alta en Dispositivos; el diálogo lo dice y
permite la captura manual (`weight_source="MANUAL"`). Cuando exista una
báscula, su lectura estable entra por el mismo campo con
`weight_source="SCALE"` — sin puertos escritos aquí (§18: nada de COM3/9600).
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QDialogButtonBox, QLabel

from frontend.desktop.components import FormField, StandardDialog, StandardForm, StatusBadge
from frontend.desktop.components.weight_input import WeightInput

WEIGHT_SOURCE_MANUAL = "MANUAL"


class WeightCaptureDialog(StandardDialog):
    def __init__(self, presenter, *, product_name: str, unit_price: Decimal | None = None,
                 unit: str = "KG", current_weight: Decimal | None = None,
                 scale_ready: bool = False, parent=None) -> None:
        super().__init__(parent, title=f"Peso — {product_name}")
        self.setObjectName("posWeightDialog")
        self._presenter = presenter
        self.weight: Decimal | None = None
        self.weight_source = WEIGHT_SOURCE_MANUAL

        if unit_price is not None:
            price = QLabel(f"Precio: ${unit_price:,.2f} / {unit}", self)
            price.setProperty("role", "subtitle")
            self.content_layout().addWidget(price)

        self._scale = StatusBadge(
            "Báscula: lista" if scale_ready else "Báscula: no configurada — captura manual",
            self, status="success" if scale_ready else "warning")
        self.content_layout().addWidget(self._scale)

        form = StandardForm(self)
        self._weight = WeightInput(self)
        if current_weight is not None:
            self._weight.set_decimal_value(current_weight)
        form.add_field("weight", FormField(f"Peso ({unit})", self._weight, required=True,
                                           helper="Kilogramos con gramos, p. ej. 1.250"))
        self.content_layout().addWidget(form)

        self._error = QLabel("", self)
        self._error.setProperty("state", "error")
        self._error.setWordWrap(True)
        self._error.hide()
        self.content_layout().addWidget(self._error)

        box = self.add_button_box(ok_text="Agregar" if current_weight is None else "Actualizar")
        box.accepted.disconnect()
        box.accepted.connect(self._submit)
        self._ok = box.button(QDialogButtonBox.Ok)
        self._weight.setFocus()
        self._weight.selectAll()

    def set_weight(self, weight: Decimal) -> None:
        """Para pruebas y para la lectura de una báscula ya estable."""
        self._weight.set_decimal_value(weight)

    def _submit(self) -> None:
        weight, reason = self._presenter.validate_weight(self._weight.decimal_value())
        if weight is None:
            self._error.setText(reason)
            self._error.show()
            return
        self.weight = weight
        self.accept()

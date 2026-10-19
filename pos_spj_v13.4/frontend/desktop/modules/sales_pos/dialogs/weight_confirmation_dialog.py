"""WeightCaptureDialog — el peso de un producto que se vende por peso (§18-19).

Re-auditoría POS (2026-10-01), medido en la base real: los 11 productos se
venden por KG y el POS agregaba "1" al hacer clic, sin preguntar el peso ni
dejar corregirlo. Este diálogo captura el peso en kilogramos (con gramos) y lo
valida el DOMINIO (`WeightPolicy`, vía el presentador) — aquí no se decide si
un peso es válido.

La lectura estable proviene del servicio de báscula configurado en Dispositivos.
La captura manual es explícita; el diálogo no decide puertos ni protocolos.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QDialogButtonBox, QLabel, QCheckBox

from frontend.desktop.components import FormField, StandardDialog, StandardForm, StatusBadge
from frontend.desktop.components.weight_input import WeightInput

WEIGHT_SOURCE_MANUAL = "MANUAL"


class WeightCaptureDialog(StandardDialog):
    def __init__(self, presenter, *, product_name: str, unit_price: Decimal | None = None,
                 unit: str = "KG", current_weight: Decimal | None = None,
                 scale_ready: bool = False, sale_id=None, product_id=None, parent=None) -> None:
        super().__init__(parent, title=f"Peso — {product_name}")
        self.setObjectName("posWeightDialog")
        self._presenter = presenter
        self.weight: Decimal | None = None
        self.weight_source = WEIGHT_SOURCE_MANUAL
        self._unit = unit
        self._sale_id, self._product_id = sale_id, product_id
        self._service = presenter.scale_service() if hasattr(presenter, "scale_service") else None

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
        self._manual = QCheckBox("Captura manual", self)
        self._manual.setChecked(not (self._service and self._service.gateway))
        self.content_layout().addWidget(self._manual)
        self._amount = QLabel("Importe estimado: no disponible", self)
        self.content_layout().addWidget(self._amount)
        self._reading_timer = QTimer(self)
        self._reading_timer.setInterval(250)
        self._reading_timer.timeout.connect(self._refresh_reading)
        self._reading_timer.start()
        self.finished.connect(self._reading_timer.stop)

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
        if not self._manual.isChecked() and self._service:
            try:
                self._weight.set_decimal_value(self._service.accepted_weight(unit=self._unit))
                self.weight_source = "SCALE"
            except ValueError as exc:
                self._error.setText(str(exc))
                self._error.show()
                return
        weight, reason = self._presenter.validate_weight(self._weight.decimal_value())
        if weight is None:
            self._error.setText(reason)
            self._error.show()
            return
        self.weight = weight
        self.accept()

    def _refresh_reading(self):
        if self._service:
            state = self._service.current()
            self._scale.setText(state.text)
            self._scale.set_status("success" if state.status == "STABLE" else "warning")
            self._weight.setEnabled(self._manual.isChecked())
            if not self._manual.isChecked():
                if state.status != "STABLE":
                    self._amount.setText("Importe estimado: esperando peso estable")
                    self._ok.setEnabled(False)
                    return
                try:
                    self._weight.set_decimal_value(self._service.accepted_weight(unit=self._unit))
                except ValueError:
                    self._ok.setEnabled(False)
                    return
        self._ok.setEnabled(True)
        if self._sale_id and self._product_id:
            quantity = self._weight.decimal_value()
            if quantity <= 0:
                self._amount.setText("Importe estimado: esperando peso positivo")
                self._quoted_quantity = None
                return
            if quantity > 0 and quantity != getattr(self, "_quoted_quantity", None):
                try:
                    amount = self._presenter.weight_amount(sale_id=self._sale_id,
                        product_id=self._product_id, quantity=quantity)
                except Exception:
                    amount = None
                self._amount.setText(f"Importe estimado: ${amount:,.2f}" if amount is not None
                                     else "Importe estimado: no disponible")
                self._quoted_quantity = quantity

"""DeliveryZoneDialog (PASS 6) — alta y edición de una zona de entrega.

Sólo captura; las reglas (códigos obligatorios, sin solapes, importes no
negativos) las aplica `zone_use_cases`, y su mensaje es el que ve el usuario.
Los campos opcionales quedan vacíos en vez de fingir un cero que significaría
otra cosa: "envío gratis desde $0" es envío siempre gratis.
"""

from __future__ import annotations

from decimal import Decimal

from frontend.desktop.components import DecimalInput, MoneyInput, StandardLineEdit
from frontend.desktop.components.dialogs import FormDialog


class DeliveryZoneDialog(FormDialog):
    def __init__(self, parent=None, *, zone=None) -> None:
        super().__init__(
            parent, title="Editar zona de entrega" if zone else "Nueva zona de entrega")
        self.name_input = StandardLineEdit(placeholder="Nombre de la zona", required=True)
        self.postal_codes_input = StandardLineEdit(
            placeholder="Códigos postales separados por coma", required=True)
        self.minimum_order_input = MoneyInput()
        self.delivery_fee_input = MoneyInput()
        self.free_threshold_input = DecimalInput(precision=2, minimum="0", nullable=True)
        self.estimated_minutes_input = DecimalInput(
            precision=0, minimum="1", nullable=True, suffix=" min")
        self.max_distance_input = DecimalInput(precision=2, nullable=True, suffix=" km")

        self.form.addRow("Nombre:", self.name_input)
        self.form.addRow("Códigos postales:", self.postal_codes_input)
        self.form.addRow("Pedido mínimo:", self.minimum_order_input)
        self.form.addRow("Costo de envío:", self.delivery_fee_input)
        self.form.addRow("Envío gratis desde (opcional):", self.free_threshold_input)
        self.form.addRow("Tiempo estimado en minutos (opcional):", self.estimated_minutes_input)
        self.form.addRow("Distancia máxima en km (opcional):", self.max_distance_input)

        box = self.add_button_box(ok_text="Guardar zona")
        box.accepted.disconnect()
        box.accepted.connect(self._accept_if_valid)
        if zone is not None:
            self.set_values(zone)

    def set_values(self, zone) -> None:
        self.name_input.setText(zone.name)
        self.postal_codes_input.setText(", ".join(zone.postal_codes))
        self.minimum_order_input.setValue(float(Decimal(str(zone.minimum_order))))
        self.delivery_fee_input.setValue(float(Decimal(str(zone.delivery_fee))))
        self.free_threshold_input.set_decimal(zone.free_delivery_threshold)
        self.estimated_minutes_input.set_decimal(zone.estimated_minutes)
        self.max_distance_input.set_decimal(zone.maximum_distance_km)

    def _is_valid(self) -> bool:
        return bool(
            self.name_input.text().strip() and self.postal_codes_input.text().strip()
            and self.free_threshold_input.is_valid()
            and self.estimated_minutes_input.is_valid()
            and self.max_distance_input.is_valid())

    def _accept_if_valid(self) -> None:
        if self._is_valid():
            self.accept()

    def data(self) -> dict:
        return {
            "name": self.name_input.text().strip(),
            "postal_codes": self.postal_codes_input.text(),
            "minimum_order": self.minimum_order_input.decimal_value(),
            "delivery_fee": self.delivery_fee_input.decimal_value(),
            "free_delivery_threshold": self.free_threshold_input.decimal_value(),
            "estimated_minutes": self.estimated_minutes_input.decimal_value(),
            "maximum_distance_km": self.max_distance_input.decimal_value(),
        }

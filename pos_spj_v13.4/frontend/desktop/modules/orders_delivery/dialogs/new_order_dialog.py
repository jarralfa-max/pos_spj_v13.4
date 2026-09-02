"""NewOrderDialog (ORD-28) — "Nuevo pedido": captures channel, fulfillment
type, contact and ONE line, then delegates to the REAL
`CreateCustomerOrderUseCase` (no SQL here, no business rules — same policy
every module's dialogs follow).

Product selection is intentionally MANUAL (`product_id` typed in, not
`ProductSearchBox`) — full product-catalog search integration is a real,
separate piece of work (a `SearchProvider` backed by the products bounded
context) this phase's scope does not extend to; documented as an honest gap,
not a silent simplification.
"""

from __future__ import annotations

from decimal import Decimal

from frontend.desktop.components import (
    DecimalInput,
    MoneyInput,
    PhoneInput,
    SearchableComboBox,
    StandardLineEdit,
)
from frontend.desktop.components.dialogs import FormDialog

_CHANNELS = [
    ("POS", "Mostrador (POS)"),
    ("WHATSAPP", "WhatsApp"),
    ("COUNTER", "Ventanilla"),
    ("PHONE", "Teléfono"),
    ("BACKOFFICE", "Backoffice"),
]

_FULFILLMENT_TYPES = [
    ("COUNTER", "Recoger en mostrador"),
    ("PICKUP", "Recoger programado"),
    ("HOME_DELIVERY", "Entrega a domicilio"),
    ("SCHEDULED_DELIVERY", "Entrega programada"),
]


class NewOrderDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nuevo pedido")
        self.channel_combo = SearchableComboBox(placeholder="Selecciona un canal")
        self.channel_combo.set_options(_CHANNELS)
        self.fulfillment_combo = SearchableComboBox(placeholder="Selecciona una modalidad")
        self.fulfillment_combo.set_options(_FULFILLMENT_TYPES)
        self.contact_name_input = StandardLineEdit(placeholder="Nombre del cliente")
        self.contact_phone_input = PhoneInput()
        self.product_id_input = StandardLineEdit(placeholder="UUID del producto")
        self.quantity_input = DecimalInput(precision=3)
        self.unit_price_input = MoneyInput()

        self.form.addRow("Canal:", self.channel_combo)
        self.form.addRow("Modalidad:", self.fulfillment_combo)
        self.form.addRow("Cliente:", self.contact_name_input)
        self.form.addRow("Teléfono:", self.contact_phone_input)
        self.form.addRow("Producto (ID):", self.product_id_input)
        self.form.addRow("Cantidad:", self.quantity_input)
        self.form.addRow("Precio unitario:", self.unit_price_input)
        box = self.add_button_box(ok_text="Crear pedido")
        box.accepted.disconnect()
        box.accepted.connect(self._accept_if_valid)

    def _is_valid(self) -> bool:
        return bool(
            self.channel_combo.current_id() and self.fulfillment_combo.current_id()
            and self.product_id_input.text().strip()
            and (self.quantity_input.decimal_value() or Decimal(0)) > 0
            and self.unit_price_input.decimal_value() >= 0)

    def _accept_if_valid(self) -> None:
        if self._is_valid():
            self.accept()

    def data(self) -> dict:
        return {
            "channel": self.channel_combo.current_id(),
            "fulfillment_type": self.fulfillment_combo.current_id(),
            "contact_name": self.contact_name_input.text().strip() or None,
            "contact_phone": self.contact_phone_input.value().strip() or None,
            "lines": [{
                "product_id": self.product_id_input.text().strip(),
                "unit_price": str(self.unit_price_input.decimal_value()),
                "requested_quantity": str(self.quantity_input.decimal_value()),
            }],
        }

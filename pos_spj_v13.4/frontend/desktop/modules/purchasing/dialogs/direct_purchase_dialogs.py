"""Dialogs for the direct-purchase page: add a cart line (supports weight/poultry),
hot authorization, and reversal reason. UI only — no business logic.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QCheckBox, QLabel

from frontend.desktop.components import (
    DecimalInput,
    FormDialog,
    StandardLineEdit,
    StandardTextArea,
)
from frontend.desktop.modules.purchasing.direct_purchase_view_models import CartLineVM


class AddCartLineDialog(FormDialog):
    """Capture one cart line. A weight/poultry line uses 3-decimal quantity in Kg
    and lets the buyer set a conversion factor to inventory units."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Agregar producto")
        self._product = StandardLineEdit(self)
        self._product.setPlaceholderText("Código o ID de producto")
        self._description = StandardLineEdit(self)
        self._description.setPlaceholderText("Descripción")
        self._is_weight = QCheckBox("Producto por peso (pollo, granel)", self)
        self._quantity = DecimalInput(self, precision=2, minimum="0")
        self._qty_label = QLabel("Cantidad", self)
        self._unit_cost = DecimalInput(self, precision=2, minimum="0", suffix="MXN")
        self._tax = DecimalInput(self, precision=2, minimum="0", suffix="MXN")
        self._discount = DecimalInput(self, precision=2, minimum="0", suffix="MXN")
        self._conversion = DecimalInput(self, precision=3, minimum="0")
        self._conversion.set_decimal("1")

        self.form.addRow("Producto", self._product)
        self.form.addRow("Descripción", self._description)
        self.form.addRow("", self._is_weight)
        self.form.addRow(self._qty_label, self._quantity)
        self.form.addRow("Costo unitario", self._unit_cost)
        self.form.addRow("IVA/Impuesto", self._tax)
        self.form.addRow("Descuento", self._discount)
        self.form.addRow("Factor de conversión", self._conversion)
        self.add_button_box(ok_text="Agregar")

        self._is_weight.toggled.connect(self._on_weight_toggled)

    def prefill_product(self, code: str) -> None:
        self._product.setText(code)
        self._description.setFocus()

    def _on_weight_toggled(self, checked: bool) -> None:
        self._quantity.set_precision(3) if hasattr(self._quantity, "set_precision") else None
        self._qty_label.setText("Peso (Kg)" if checked else "Cantidad")

    def line(self) -> CartLineVM | None:
        product_id = self._product.text().strip()
        quantity = self._quantity.decimal_value()
        unit_cost = self._unit_cost.decimal_value()
        if not product_id or quantity is None or quantity <= 0 or unit_cost is None:
            return None
        weight = self._is_weight.isChecked()
        return CartLineVM(
            product_id=product_id,
            description=self._description.text().strip() or product_id,
            quantity=quantity, unit_cost=unit_cost,
            tax=self._tax.decimal_value() or Decimal("0"),
            discount=self._discount.decimal_value() or Decimal("0"),
            purchase_unit="KG" if weight else "PZA",
            inventory_unit="KG" if weight else "PZA",
            conversion_factor=self._conversion.decimal_value() or Decimal("1"),
            is_weight=weight)


class HotAuthorizationDialog(FormDialog):
    """A second user authorizes an over-limit purchase in place (§64)."""

    def __init__(self, parent=None, *, amount: str = "") -> None:
        super().__init__(parent, title="Autorización en caliente")
        if amount:
            self.form.addRow("Monto", QLabel(amount, self))
        self._reason = StandardTextArea(self)
        self._reason.setPlaceholderText("Motivo de la autorización (obligatorio)")
        self.form.addRow("Motivo", self._reason)
        self.add_button_box(ok_text="Autorizar")

    def reason(self) -> str:
        return self._reason.toPlainText().strip()


class ReverseReasonDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Reversar compra")
        self._reason = StandardTextArea(self)
        self._reason.setPlaceholderText("Motivo del reverso (obligatorio)")
        self.form.addRow("Motivo", self._reason)
        self.add_button_box(ok_text="Reversar")

    def reason(self) -> str:
        return self._reason.toPlainText().strip()

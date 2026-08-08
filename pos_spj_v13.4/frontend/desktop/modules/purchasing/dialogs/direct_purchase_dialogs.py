"""Dialogs for the direct-purchase page: add a cart line (supports weight/poultry),
hot authorization, and reversal reason. UI only — no business logic.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QCheckBox, QLabel

from frontend.desktop.components import (
    DecimalInput,
    EntitySearchInput,
    FormDialog,
    StandardLineEdit,
    StandardTextArea,
)
from frontend.desktop.modules.purchasing.direct_purchase_view_models import CartLineVM


class AddCartLineDialog(FormDialog):
    """Capture one cart line. A weight/poultry line uses 3-decimal quantity in Kg
    and lets the buyer set a conversion factor to inventory units."""

    def __init__(self, parent=None, *, product_provider=None, cost_variance=None) -> None:
        super().__init__(parent, title="Agregar producto")
        self._provider = product_provider or (lambda _q: [])
        self._cost_variance = cost_variance or (lambda _pid, _cost: {
            "label": "—", "is_significant": False})
        self._product = EntitySearchInput(
            self, provider=self._provider, placeholder="Buscar producto por nombre o código")
        self._product.selected.connect(lambda _id: self._update_cost_hint())
        self._description = StandardLineEdit(self)
        self._description.setPlaceholderText("Descripción")
        self._is_weight = QCheckBox("Producto por peso (pollo, granel)", self)
        self._quantity = DecimalInput(self, precision=2, minimum="0")
        self._qty_label = QLabel("Cantidad", self)
        self._unit_cost = DecimalInput(self, precision=2, minimum="0", suffix="MXN")
        self._unit_cost.value_changed.connect(self._update_cost_hint)
        self._cost_hint = QLabel("", self)
        self._cost_hint.setProperty("role", "muted")
        self._tax = DecimalInput(self, precision=2, minimum="0", suffix="MXN")
        self._discount = DecimalInput(self, precision=2, minimum="0", suffix="MXN")
        self._conversion = DecimalInput(self, precision=3, minimum="0")
        self._conversion.set_decimal("1")

        self.form.addRow("Producto", self._product)
        self.form.addRow("Descripción", self._description)
        self.form.addRow("", self._is_weight)
        self.form.addRow(self._qty_label, self._quantity)
        self.form.addRow("Costo unitario", self._unit_cost)
        self.form.addRow("Referencia", self._cost_hint)
        self.form.addRow("IVA/Impuesto", self._tax)
        self.form.addRow("Descuento", self._discount)
        self.form.addRow("Factor de conversión", self._conversion)
        self.add_button_box(ok_text="Agregar")

        self._is_weight.toggled.connect(self._on_weight_toggled)

    def prefill_product(self, code: str) -> None:
        """A barcode scan supplies a code, not a canonical id — resolve it
        through the same catalog search rather than trusting it as an id."""
        matches = list(self._provider(code))
        if len(matches) == 1:
            self._product.set_selected_label(matches[0].id, matches[0].label)
            self._update_cost_hint()
        self._description.setFocus()

    def _update_cost_hint(self) -> None:
        product_id = self._product.selected_id()
        cost = self._unit_cost.decimal_value()
        if not product_id or cost is None or cost <= 0:
            self._cost_hint.setText("")
            self._cost_hint.setProperty("role", "muted")
            return
        result = self._cost_variance(str(product_id), cost)
        # result["label"] already carries its own visual emphasis (e.g. "▲ SUBIÓ
        # 25.0%") for significant variances — no separate danger role exists in
        # the design system's QSS to layer on top of it.
        self._cost_hint.setText(f"Costo de referencia — {result['label']}")

    def _on_weight_toggled(self, checked: bool) -> None:
        self._quantity.set_precision(3) if hasattr(self._quantity, "set_precision") else None
        self._qty_label.setText("Peso (Kg)" if checked else "Cantidad")

    def line(self) -> CartLineVM | None:
        product_id = self._product.selected_id()
        quantity = self._quantity.decimal_value()
        unit_cost = self._unit_cost.decimal_value()
        if not product_id or quantity is None or quantity <= 0 or unit_cost is None:
            return None
        weight = self._is_weight.isChecked()
        return CartLineVM(
            product_id=str(product_id),
            description=self._description.text().strip() or self._product.selected_label(),
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

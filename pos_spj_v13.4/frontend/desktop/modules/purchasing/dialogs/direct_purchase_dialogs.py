"""Dialogs for the direct-purchase page: add a cart line (units from Products),
hot authorization, and reversal reason. UI only — no business logic.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QDialogButtonBox, QLabel

from frontend.desktop.components import (
    DecimalInput,
    EntitySearchInput,
    FormDialog,
    SearchableComboBox,
    StandardTextArea,
)
from frontend.desktop.modules.purchasing.direct_purchase_view_models import (
    CartLineVM,
    error_text,
)


def _inline_error_label(parent) -> QLabel:
    """Etiqueta de error en línea del Design System (`state="error"`)."""
    label = QLabel("", parent)
    label.setWordWrap(True)
    label.setProperty("state", "error")
    label.hide()
    return label


class AddCartLineDialog(FormDialog):
    """Captura una línea. Unidad de compra, unidad de inventario y conversión
    salen del maestro de Productos (``profile_provider``): aquí sólo se ELIGE entre
    las presentaciones configuradas, nunca se escribe un factor ni se marca "por
    peso" a mano. La precisión de la cantidad sigue a la dimensión de la unidad."""

    def __init__(self, parent=None, *, product_provider=None, cost_variance=None,
                 empty_reason_provider=None, profile_provider=None) -> None:
        super().__init__(parent, title="Agregar producto")
        self._provider = product_provider or (lambda _q: [])
        self._profile_provider = profile_provider or (lambda _pid: None)
        self._profile = None
        self._cost_variance = cost_variance or (lambda _pid, _cost: {
            "label": "—", "is_significant": False})
        self._product = EntitySearchInput(
            self, provider=self._provider, placeholder="Buscar producto por nombre o código",
            empty_reason_provider=empty_reason_provider)
        self._product.selected.connect(lambda _id: self._product_changed())
        self._unit = SearchableComboBox(self, placeholder="Unidad de compra")
        self._unit.selection_changed.connect(lambda *_: self._unit_changed())
        self._conversion_hint = QLabel("", self)
        self._conversion_hint.setProperty("role", "muted")
        self._conversion_hint.setWordWrap(True)
        self._quantity = DecimalInput(self, precision=3, minimum="0")
        self._quantity.value_changed.connect(self._update_conversion_hint)
        # Peso variable (§17): sólo aparece si Productos marca el producto así.
        self._weight_label = QLabel("Peso real (kg)", self)
        self._weight = DecimalInput(self, precision=3, minimum="0", nullable=True)
        self._weight.value_changed.connect(self._update_conversion_hint)
        self._unit_cost = DecimalInput(self, precision=2, minimum="0", suffix="MXN")
        self._unit_cost.value_changed.connect(self._update_cost_hint)
        self._cost_label = QLabel("Costo unitario", self)
        self._cost_hint = QLabel("", self)
        self._cost_hint.setProperty("role", "muted")
        self._tax = DecimalInput(self, precision=2, minimum="0", suffix="MXN")
        self._discount = DecimalInput(self, precision=2, minimum="0", suffix="MXN")

        self.form.addRow("Producto", self._product)
        self.form.addRow("Unidad de compra", self._unit)
        self.form.addRow("", self._conversion_hint)
        self.form.addRow("Cantidad", self._quantity)
        self.form.addRow(self._weight_label, self._weight)
        self._weight_label.setVisible(False)
        self._weight.setVisible(False)
        self.form.addRow(self._cost_label, self._unit_cost)
        self.form.addRow("Referencia", self._cost_hint)
        self.form.addRow("IVA/Impuesto", self._tax)
        self.form.addRow("Descuento", self._discount)
        self._error = _inline_error_label(self)
        self._root.addWidget(self._error)
        self.add_button_box(ok_text="Agregar")

    def prefill_product(self, code: str) -> None:
        """A barcode scan supplies a code, not a canonical id — resolve it
        through the same catalog search rather than trusting it as an id."""
        matches = list(self._provider(code))
        if len(matches) == 1:
            self._product.set_selected_label(matches[0].id, matches[0].label)
            self._product_changed()
        self._quantity.setFocus()

    # perfil de compra (Productos) ---------------------------------------------
    def _product_changed(self) -> None:
        product_id = self._product.selected_id()
        self._profile = self._profile_provider(str(product_id)) if product_id else None
        units = list(self._profile.units) if self._profile is not None else []
        self._unit.set_options([(u.code, _unit_label(u, self._profile)) for u in units])
        if units:
            base = next((u for u in units if u.is_base), units[0])
            self._unit.set_current_id(base.code)
        self._unit.setEnabled(len(units) > 1)
        weighed = self._variable_weight()
        self._weight_label.setVisible(weighed)
        self._weight.setVisible(weighed)
        self._unit_changed()
        self._update_cost_hint()

    def _variable_weight(self) -> bool:
        return bool(self._profile is not None and getattr(self._profile, "catch_weight", False))

    def _priced_by_weight(self) -> bool:
        basis = getattr(self._profile, "price_basis", None) or "PER_KILOGRAM"
        return self._variable_weight() and basis == "PER_KILOGRAM"

    def _selected_unit(self):
        if self._profile is None:
            return None
        return self._profile.unit(self._unit.current_id())

    def _unit_changed(self) -> None:
        unit = self._selected_unit()
        weight = unit is not None and unit.dimension == "WEIGHT"
        self._quantity.set_precision(3 if weight or unit is None else 2)
        name = unit.name if unit is not None else "unidad"
        self._cost_label.setText("Costo por kg" if self._priced_by_weight()
                                 else f"Costo por {name.lower()}")
        self._update_conversion_hint()

    def _update_conversion_hint(self) -> None:
        unit, profile = self._selected_unit(), self._profile
        if profile is None or unit is None:
            self._conversion_hint.setText("")
            return
        if self._variable_weight():
            text = "Peso variable: captura el peso real de la báscula"
            if self._priced_by_weight():
                text += "; el importe es peso × costo por kg"
            if getattr(profile, "base_unit_dimension", "") == "WEIGHT":
                text += f" y entra a inventario el peso real en {profile.base_unit}"
            self._conversion_hint.setText(text + ".")
            return
        if unit.is_base:
            self._conversion_hint.setText(f"Entra a inventario en {profile.base_unit_name}.")
            return
        text = f"1 {unit.name} = {_plain(unit.factor_to_base)} {profile.base_unit}"
        quantity = self._quantity.decimal_value()
        if quantity:
            text += (f" · entran {_plain(quantity * unit.factor_to_base)} "
                     f"{profile.base_unit} a inventario")
        self._conversion_hint.setText(text + ".")

    def _update_cost_hint(self) -> None:
        product_id = self._product.selected_id()
        cost = self._unit_cost.decimal_value()
        if not product_id or cost is None or cost <= 0:
            self._cost_hint.setText("")
            return
        result = self._cost_variance(str(product_id), cost)
        # result["label"] already carries its own visual emphasis (e.g. "▲ SUBIÓ
        # 25.0%") for significant variances — no separate danger role exists in
        # the design system's QSS to layer on top of it.
        self._cost_hint.setText(f"Costo de referencia — {result['label']}")

    # validación ----------------------------------------------------------------
    def validation_message(self) -> str | None:
        """Por qué la línea no se puede agregar (None si es válida). El dominio
        exige cantidad y costo MAYORES a cero; se dice aquí, en línea, y no
        después de que el guardado la rechace."""
        if not self._product.selected_id():
            return "Selecciona un producto del catálogo."
        if self._profile is not None and self._selected_unit() is None:
            return "Elige la unidad de compra."
        quantity = self._quantity.decimal_value()
        if quantity is None or quantity <= 0:
            return "La cantidad debe ser mayor a cero."
        unit_cost = self._unit_cost.decimal_value()
        if unit_cost is None or unit_cost <= 0:
            return "El costo unitario debe ser mayor a cero."
        if self._variable_weight() and not (self._weight.decimal_value() or 0) > 0:
            return "Producto de peso variable: captura el peso real (kg)."
        return None

    def error_text(self) -> str:
        return self._error.text()

    def accept(self) -> None:
        problem = self.validation_message()
        if problem:
            self._error.setText(problem)
            self._error.show()
            return
        self._error.hide()
        super().accept()

    def line(self) -> CartLineVM | None:
        if self.validation_message() is not None:
            return None
        unit, profile = self._selected_unit(), self._profile
        # Sin perfil la unidad queda vacía = unidad base: el caso de uso la
        # resuelve contra Productos al guardar.
        return CartLineVM(
            product_id=str(self._product.selected_id()),
            description=self._product.selected_label(),
            quantity=self._quantity.decimal_value(),
            unit_cost=self._unit_cost.decimal_value(),
            tax=self._tax.decimal_value() or Decimal("0"),
            discount=self._discount.decimal_value() or Decimal("0"),
            purchase_unit=unit.code if unit is not None else "",
            inventory_unit=profile.base_unit if profile is not None else "",
            conversion_factor=unit.factor_to_base if unit is not None else Decimal("1"),
            is_weight=unit is not None and unit.dimension == "WEIGHT",
            net_weight=self._weight.decimal_value() if self._variable_weight() else None,
            priced_by_weight=self._priced_by_weight())


def _plain(value) -> str:
    return format(Decimal(value).normalize(), "f")


def _unit_label(unit, profile) -> str:
    if unit.is_base:
        return f"{unit.name} (unidad base)"
    return f"{unit.name} — {_plain(unit.factor_to_base)} {profile.base_unit}"


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


class EditLineCostDialog(FormDialog):
    """Captura el costo de una línea que llegó sin él (p. ej. de una solicitud
    aprobada sin costo estimado). El costo debe ser mayor a cero."""

    def __init__(self, parent=None, *, description: str = "",
                 current_cost: Decimal | None = None) -> None:
        super().__init__(parent, title="Costo unitario")
        if description:
            self.form.addRow("Producto", QLabel(description, self))
        self._cost = DecimalInput(self, precision=2, minimum="0", suffix="MXN")
        if current_cost is not None and current_cost > 0:
            self._cost.set_decimal(current_cost)
        self.form.addRow("Costo unitario", self._cost)
        self._error = _inline_error_label(self)
        self._root.addWidget(self._error)
        self.add_button_box(ok_text="Guardar costo")

    def unit_cost(self) -> Decimal | None:
        value = self._cost.decimal_value()
        return value if value is not None and value > 0 else None

    def error_text(self) -> str:
        return self._error.text()

    def accept(self) -> None:
        if self.unit_cost() is None:
            self._error.setText("El costo unitario debe ser mayor a cero.")
            self._error.show()
            return
        self._error.hide()
        super().accept()


class ConfirmDirectPurchaseDialog(FormDialog):
    """Confirma una compra de contado: muestra a qué se compromete el usuario
    (proveedor, sucursal, almacén, total, condición — con NOMBRES, nunca ids) y
    exige elegir la fuente de pago. No se puede aceptar sin una fuente válida.
    """

    def __init__(self, parent=None, *, summary) -> None:
        super().__init__(parent, title="Confirmar compra")
        self._summary = summary
        for title, value in (("Folio", summary.document_number),
                             ("Proveedor", summary.supplier),
                             ("Sucursal", summary.branch),
                             ("Almacén", summary.warehouse),
                             ("Total", summary.total),
                             ("Condición", summary.condition_label)):
            label = QLabel(str(value or "—"), self)
            label.setWordWrap(True)
            self.form.addRow(title, label)
        self._source = SearchableComboBox(self, placeholder="Selecciona la fuente de pago")
        self._source.set_options(list(summary.payment_sources))
        if summary.requires_payment_source:
            self.form.addRow("Fuente de pago", self._source)
        self._error = _inline_error_label(self)
        self._root.addWidget(self._error)
        box = self.add_button_box(ok_text="Confirmar compra")
        self._ok = box.button(QDialogButtonBox.Ok)
        if summary.requires_payment_source and not summary.payment_sources:
            # Ninguna fuente se puede asentar en esta instalación: mejor decirlo
            # aquí que dejar confirmar y que el dinero salga sin asiento.
            self._error.setText(
                "Finanzas no tiene configurada una fuente de pago que se pueda "
                "contabilizar. Registra la compra a crédito o configura la cuenta.")
            self._error.show()
            self._ok.setEnabled(False)

    def payment_source(self) -> str | None:
        if not self._summary.requires_payment_source:
            return None
        return self._source.current_id() or None

    def error_text(self) -> str:
        return self._error.text()

    def accept(self) -> None:
        if self._summary.requires_payment_source and not self.payment_source():
            self._error.setText("Selecciona la fuente de pago para confirmar la compra.")
            self._error.show()
            return
        self._error.hide()
        super().accept()


def confirm_purchase_flow(parent, presenter, direct_purchase_id: str,
                          operation_id: str | None = None):
    """Confirma una compra pidiendo la fuente de pago SÓLO si hace falta.

    Devuelve `(ok, mensaje, datos)` — o `None` si el usuario cancela el diálogo.
    Compartido por el Historial y la pantalla de captura: la regla "contado exige
    fuente; crédito no" vive en un solo lugar.
    """
    summary = presenter.confirmation_summary(direct_purchase_id)
    if summary is None:
        return False, "La compra no existe.", {"error_code": "NOT_FOUND"}
    if summary.status == "PENDING_AUTHORIZATION":
        data = {"error_code": "AUTHORIZATION_REQUIRED"}
        return False, error_text("", data), data
    source = None
    if summary.requires_payment_source:
        dialog = ConfirmDirectPurchaseDialog(parent, summary=summary)
        if not dialog.exec_():
            return None
        source = dialog.payment_source()
        if not source:
            return None
    return presenter.confirm(direct_purchase_id, source, operation_id=operation_id)

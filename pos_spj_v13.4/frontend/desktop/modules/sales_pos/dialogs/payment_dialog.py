"""PaymentDialog (POS-22 prerequisite) — the real payment-collection UI this
tree was missing since SALES-19: nothing in `sales_pos/` ever called
`SalesPosPresenter.record_payment()`/`begin_checkout()` before this, so
"Cobrar" always failed against SALES-13/14's real `SalePaymentPolicy.
ensure_fully_paid` gate (0 recorded < any positive total). Confirmed by
reading `checkout_use_cases.py::CheckoutSaleUseCase` directly before writing
this: it re-checks `ensure_fully_paid` itself, so this dialog is not
optional plumbing, it is the only way "Cobrar" can ever legally succeed.

Legacy's `presentation/sales/dialogs/payment_dialog.py::DialogoPago` computes
change/mixed-split/credit-limit validation itself, client-side, then submits
one shot via `finalizar_venta` — exactly the "lógica de pago en la UI" POS-22
asks to eliminate. This dialog does none of that: it only collects
method/amount/reference per payment line locally and lets the real domain
policies (`SalePaymentPolicy`, `CreditNotAuthorizedError` via
`SalesCreditClient`) accept or reject each one when submitted. "Pago Mixto"
needs no dedicated option here either — it is not a `PaymentMethod` in the
new aggregate, it is what a sale becomes the moment a second distinct method
is recorded (`Sale.is_mixed_payment`) — the cashier just adds two lines with
different methods.

**Why nothing touches the backend until "Confirmar y cobrar" is clicked**:
`backend/domain/sales/policies/lifecycle_policies.py`'s transition table has
`(ACTIVE, CHECKOUT_PENDING)` and `(CHECKOUT_PENDING, CANCELLED)`, but no
`(CHECKOUT_PENDING, ACTIVE)` — once `begin_checkout()` succeeds there is no
way back to an editable cart short of cancelling the whole sale. Calling it
eagerly (e.g. when this dialog opens) would strand the sale in
CHECKOUT_PENDING the moment the cashier clicks "Cancelar" here, unlike the
legacy dialog where Cancelar always just returns to the cart untouched. So
`begin_checkout()` is deferred to the same moment the payment lines are
already collected and balanced — cancelling before that point never calls
the backend at all, matching the legacy dialog's real behavior.

Mercado Pago intentionally has no link-generation flow here — SALES-13's own
documented scope is that the new aggregate only records an ALREADY-CONFIRMED
MP payment, the same shape as Card/Transfer (a real, working link-generation
flow already exists on the legacy stack, `services/mercado_pago_service.py`,
and rebuilding it is out of scope for this dialog). Selecting it asks for the
MP payment/folio id as the reference field, it does not create a new charge.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt5.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout,
)

from frontend.desktop.components import (
    MoneyInput,
    StandardLineEdit,
    create_danger_button,
    create_secondary_button,
    create_success_button,
)

_METHOD_LABELS = {
    "CASH": "Efectivo",
    "CARD": "Tarjeta",
    "TRANSFER": "Transferencia",
    "CREDIT": "Crédito",
    "MERCADO_PAGO": "Mercado Pago",
}


class PaymentDialog(QDialog):
    def __init__(self, presenter, *, sale_id: str, total_due: Decimal, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posPaymentDialog")
        self.setWindowTitle("Cobrar")
        self.setModal(True)
        self._presenter = presenter
        self._sale_id = sale_id
        self._total_due = total_due
        self._lines: list[tuple[str, Decimal, str | None]] = []
        self.completed = False

        root = QVBoxLayout(self)

        self._lbl_total = QLabel(f"Total a pagar: ${total_due:.2f}")
        self._lbl_total.setObjectName("posPaymentTotal")
        root.addWidget(self._lbl_total)

        self._lbl_remaining = QLabel(self)
        root.addWidget(self._lbl_remaining)

        add_row = QHBoxLayout()
        self._method = QComboBox(self)
        for code, label in _METHOD_LABELS.items():
            self._method.addItem(label, code)
        add_row.addWidget(self._method)

        self._amount = MoneyInput(self)
        add_row.addWidget(self._amount)

        self._reference = StandardLineEdit(self, placeholder="Referencia (opcional)")
        add_row.addWidget(self._reference)

        self._btn_add = create_secondary_button(self, "+ Agregar pago")
        self._btn_add.clicked.connect(self._add_line)
        add_row.addWidget(self._btn_add)
        root.addLayout(add_row)

        self._mp_hint = QLabel(
            "Mercado Pago: registra un pago ya confirmado (folio/id como referencia). "
            "No genera un nuevo link de cobro aquí.")
        self._mp_hint.setObjectName("posPaymentMpHint")
        self._mp_hint.setWordWrap(True)
        self._mp_hint.setVisible(False)
        root.addWidget(self._mp_hint)

        self._list = QListWidget(self)
        root.addWidget(self._list, stretch=1)

        self._btn_remove = create_danger_button(self, "Quitar seleccionado")
        self._btn_remove.clicked.connect(self._remove_selected)
        root.addWidget(self._btn_remove)

        actions = QHBoxLayout()
        btn_cancel = create_secondary_button(self, "Cancelar")
        btn_cancel.clicked.connect(self.reject)
        actions.addWidget(btn_cancel)

        self._btn_confirm = create_success_button(self, "💰 Confirmar y cobrar")
        self._btn_confirm.clicked.connect(self._confirm)
        actions.addWidget(self._btn_confirm)
        root.addLayout(actions)

        self._method.currentIndexChanged.connect(self._on_method_changed)
        self._on_method_changed()
        self._refresh_remaining()

    # ── local, non-persisted payment lines ────────────────────────────────

    def _on_method_changed(self) -> None:
        method = self._method.currentData()
        remaining = self._remaining()
        self._amount.setValue(float(remaining) if remaining > 0 else 0.0)
        self._reference.setText("")
        self._mp_hint.setVisible(method == "MERCADO_PAGO")

    def _remaining(self) -> Decimal:
        recorded = sum((amount for _, amount, _ in self._lines), Decimal("0"))
        return self._total_due - recorded

    def _refresh_remaining(self) -> None:
        remaining = self._remaining()
        shown = remaining if remaining > 0 else Decimal("0")
        self._lbl_remaining.setText(f"Restante: ${shown:.2f}")
        self._btn_confirm.setEnabled(remaining <= 0 and bool(self._lines))

    def _add_line(self) -> None:
        try:
            amount = Decimal(str(self._amount.value() or "0"))
        except (InvalidOperation, TypeError):
            return
        if amount <= 0:
            return
        method = self._method.currentData()
        reference = self._reference.value() or None
        self._lines.append((method, amount, reference))
        label = f"{_METHOD_LABELS[method]}: ${amount:.2f}"
        if reference:
            label += f" ({reference})"
        self._list.addItem(QListWidgetItem(label))
        self._refresh_remaining()
        self._on_method_changed()

    def _remove_selected(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        self._list.takeItem(row)
        del self._lines[row]
        self._refresh_remaining()

    # ── real submission, only on confirm — see module docstring for why ───

    def _confirm(self) -> None:
        self._btn_confirm.setEnabled(False)

        checkout = self._presenter.begin_checkout(sale_id=self._sale_id)
        if not checkout.success:
            QMessageBox.warning(self, "No se pudo iniciar el cobro", checkout.message)
            self._btn_confirm.setEnabled(True)
            return

        for method, amount, reference in self._lines:
            result = self._presenter.record_payment(
                sale_id=self._sale_id, method=method, amount=amount, reference=reference)
            if not result.success:
                QMessageBox.warning(
                    self, "Pago no registrado",
                    f"{result.message}\n\nLos pagos ya registrados quedan aplicados a la venta; "
                    "puede reintentar el pago restante o cancelar la venta completa desde "
                    "\"Cancelar\" en la pantalla principal.")
                self._btn_confirm.setEnabled(True)
                return

        result = self._presenter.checkout_sale(sale_id=self._sale_id)
        if not result.success:
            QMessageBox.warning(self, "No se pudo finalizar la venta", result.message)
            self._btn_confirm.setEnabled(True)
            return

        self.completed = True
        self.accept()

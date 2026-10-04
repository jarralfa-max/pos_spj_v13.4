"""PaymentDialog — el cobro modal (§30): total prominente, forma de pago, monto
recibido, cambio, cancelar y confirmar.

Recoge líneas de pago localmente y sólo al confirmar las aplica, en este
orden: iniciar cobro → registrar cada pago → completar. `CHECKOUT_PENDING` no
tiene vuelta a `ACTIVE`, así que nada toca el backend antes de "Confirmar":
cancelar aquí deja el carrito intacto. Un reintento tras un fallo (sin
existencia, sin turno) no vuelve a iniciar el cobro ni duplica pagos.

Ninguna regla de pago vive aquí:

* el CAMBIO lo calcula `CashPaymentPolicy` (§32) vía el presentador — antes no
  se mostraba en absoluto: el cajero no sabía cuánto devolver;
* "sólo el efectivo admite cambio" es `SalePaymentPolicy.ensure_amount_allowed`
  y se consulta ANTES de iniciar el cobro (una tarjeta por más de lo que falta
  dejaba un "cambio" que el cobro descontaba de un efectivo inexistente);
* los métodos visibles son los que el usuario puede cobrar; Crédito sólo con
  cliente asignado (§36), y si su línea alcanza lo decide el caso de uso.

"Pago mixto" no es un método: es lo que una venta es cuando registra dos
métodos distintos (`Sale.is_mixed_payment`). Mercado Pago registra un pago YA
confirmado (folio como referencia); la liga de cobro es de Pagos (§35).
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout,
)

from frontend.desktop.components import (
    MoneyInput,
    StandardLineEdit,
    create_danger_button,
    create_primary_button,
    create_secondary_button,
)

METHOD_LABELS = {
    "CASH": "Efectivo",
    "CARD": "Tarjeta",
    "TRANSFER": "Transferencia",
    "CREDIT": "Crédito",
    "MERCADO_PAGO": "Mercado Pago",
    "VOUCHER": "Vale / saldo a favor",
}


class PaymentDialog(QDialog):
    def __init__(self, presenter, *, sale_id: str, total_due: Decimal,
                 has_customer: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posPaymentDialog")
        self.setWindowTitle("Cobrar")
        self.setModal(True)
        self._presenter = presenter
        self._sale_id = sale_id
        self._total_due = Decimal(str(total_due))
        self._lines: list[tuple[str, Decimal, str | None]] = []
        self.completed = False
        self.change = Decimal("0")
        #: Avance ya aplicado al backend (ver docstring del módulo).
        self._checkout_started = False
        self._recorded = 0

        root = QVBoxLayout(self)

        self._lbl_total = QLabel(f"Total a pagar: ${self._total_due:,.2f}")
        self._lbl_total.setObjectName("posPaymentTotal")
        self._lbl_total.setProperty("role", "amount")
        root.addWidget(self._lbl_total)

        self._lbl_remaining = QLabel(self)
        self._lbl_remaining.setObjectName("posPaymentRemaining")
        root.addWidget(self._lbl_remaining)
        self._lbl_change = QLabel(self)
        self._lbl_change.setObjectName("posPaymentChange")
        self._lbl_change.setProperty("role", "amount")
        root.addWidget(self._lbl_change)

        add_row = QHBoxLayout()
        self._method = QComboBox(self)
        self._method.setObjectName("posPaymentMethod")
        for code in presenter.payment_methods(has_customer=has_customer):
            self._method.addItem(METHOD_LABELS.get(code, code), code)
        add_row.addWidget(self._method)

        self._amount = MoneyInput(self)
        self._amount.setObjectName("posPaymentAmount")
        add_row.addWidget(self._amount)

        self._reference = StandardLineEdit(self, placeholder="Referencia (opcional)")
        add_row.addWidget(self._reference)

        self._btn_add = create_secondary_button(self, "Agregar pago")
        self._btn_add.clicked.connect(self._add_line)
        add_row.addWidget(self._btn_add)
        root.addLayout(add_row)

        self._hint = QLabel("", self)
        self._hint.setObjectName("posPaymentHint")
        self._hint.setWordWrap(True)
        self._hint.setVisible(False)
        root.addWidget(self._hint)

        self._list = QListWidget(self)
        root.addWidget(self._list, stretch=1)

        self._btn_remove = create_danger_button(self, "Quitar pago seleccionado")
        self._btn_remove.clicked.connect(self._remove_selected)
        root.addWidget(self._btn_remove)

        actions = QHBoxLayout()
        btn_cancel = create_secondary_button(self, "Cancelar")
        btn_cancel.clicked.connect(self.reject)
        actions.addWidget(btn_cancel)

        self._btn_confirm = create_primary_button(self, "Confirmar y cobrar")
        self._btn_confirm.setObjectName("posPaymentConfirm")
        self._btn_confirm.setProperty("emphasis", "dominant")
        self._btn_confirm.clicked.connect(self._confirm)
        actions.addWidget(self._btn_confirm, stretch=1)
        root.addLayout(actions)

        self._method.currentIndexChanged.connect(self._on_method_changed)
        self._on_method_changed()
        self._refresh_remaining()

    # ── líneas de pago locales (no persistidas hasta confirmar) ──────────
    def set_amount(self, amount: Decimal) -> None:
        self._amount.set_decimal_value(amount)

    def select_method(self, code: str) -> None:
        index = self._method.findData(code)
        if index >= 0:
            self._method.setCurrentIndex(index)

    def _recorded_total(self) -> Decimal:
        return sum((amount for _, amount, _ in self._lines), Decimal("0"))

    def _remaining(self) -> Decimal:
        return self._total_due - self._recorded_total()

    def _on_method_changed(self) -> None:
        method = self._method.currentData()
        remaining = self._remaining()
        self._amount.set_decimal_value(remaining if remaining > 0 else Decimal("0"))
        self._reference.setText("")
        if method == "MERCADO_PAGO":
            self._show_hint("Mercado Pago: registra un pago ya confirmado (folio como "
                            "referencia). La liga de cobro no se genera aquí.")
        elif method == "CREDIT":
            self._show_hint("Crédito: se valida la línea del cliente al confirmar.")
        elif method == "VOUCHER":
            self._show_hint("Vale: escribe o escanea el código en «Referencia»; se cobra hasta "
                            "su saldo y no entra efectivo al cajón.")
        else:
            self._hint.setVisible(False)

    def _show_hint(self, text: str) -> None:
        self._hint.setText(text)
        self._hint.setVisible(True)

    def _refresh_remaining(self) -> None:
        remaining = self._remaining()
        shown = remaining if remaining > 0 else Decimal("0")
        self._lbl_remaining.setText(f"Restante: ${shown:,.2f}")
        tender = self._presenter.cash_tender(total=self._total_due, received=self._recorded_total())
        has_cash = any(method == "CASH" for method, _, _ in self._lines)
        self.change = tender.change if (tender is not None and has_cash) else Decimal("0")
        self._lbl_change.setText(f"Cambio: ${self.change:,.2f}")
        self._lbl_change.setVisible(self.change > 0)
        self._btn_confirm.setEnabled(remaining <= 0 and bool(self._lines))

    def _add_line(self) -> None:
        amount = self._amount.decimal_value()
        if amount <= 0:
            self._show_hint("Captura un monto mayor a cero.")
            return
        method = self._method.currentData()
        if method is None:
            self._show_hint("No tienes permiso para cobrar con ningún método.")
            return
        problema = self._presenter.payment_amount_problem(
            method=method, amount=amount, outstanding=self._remaining())
        if problema:
            self._show_hint(problema)
            return
        reference = self._reference.value() or None
        if method == "VOUCHER":
            if not reference:
                self._show_hint("Captura el código del vale en «Referencia».")
                return
            if any(m == "VOUCHER" and r == reference for m, _, r in self._lines):
                self._show_hint("Ese vale ya está en los pagos.")
                return
            saldo = self._presenter.voucher_balance(reference)
            if saldo is not None:
                if not saldo.get("found"):
                    self._show_hint(f"No existe un vale con el código {reference}.")
                    return
                if Decimal(str(saldo.get("balance") or 0)) <= 0:
                    self._show_hint("El vale no tiene saldo.")
                    return
                amount = min(amount, Decimal(str(saldo["balance"])))
        self._lines.append((method, amount, reference))
        label = f"{METHOD_LABELS.get(method, method)}: ${amount:,.2f}"
        if reference:
            label += f" ({reference})"
        self._list.addItem(QListWidgetItem(label))
        self._refresh_remaining()
        self._on_method_changed()

    def _remove_selected(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        if row < self._recorded:
            self._show_hint("Ese pago ya quedó registrado en la venta; no se puede quitar aquí.")
            return
        self._list.takeItem(row)
        del self._lines[row]
        self._refresh_remaining()

    # ── aplicación real, sólo al confirmar ───────────────────────────────
    def _confirm(self) -> None:
        self._btn_confirm.setEnabled(False)

        if not self._checkout_started:
            checkout = self._presenter.begin_checkout(sale_id=self._sale_id)
            if not checkout.success:
                QMessageBox.warning(self, "No se pudo iniciar el cobro", checkout.message)
                self._btn_confirm.setEnabled(True)
                return
            self._checkout_started = True

        while self._recorded < len(self._lines):
            method, amount, reference = self._lines[self._recorded]
            result = self._presenter.record_payment(
                sale_id=self._sale_id, method=method, amount=amount, reference=reference)
            if not result.success:
                QMessageBox.warning(
                    self, "Pago no registrado",
                    f"{result.message}\n\nLos pagos ya registrados quedan aplicados a la venta; "
                    "puedes corregir el pago restante o cancelar la venta completa desde "
                    "«Cancelar» en la pantalla principal.")
                self._btn_confirm.setEnabled(True)
                return
            self._recorded += 1

        result = self._presenter.checkout_sale(sale_id=self._sale_id)
        if not result.success and result.error_code == "STOCK_AUTHORIZATION_REQUIRED":
            # Fase 6: sin existencia suficiente, sólo con autorización en caliente.
            from frontend.desktop.modules.sales_pos.dialogs.stock_authorization_dialog import (
                StockAuthorizationDialog,
            )
            dialog = StockAuthorizationDialog(self._presenter, message=result.message, parent=self)
            if dialog.exec_() and dialog.authorizer_user_id:
                result = self._presenter.checkout_sale(
                    sale_id=self._sale_id, authorizer_user_id=dialog.authorizer_user_id,
                    reason=dialog.reason)
        if not result.success:
            QMessageBox.warning(self, "No se pudo finalizar la venta", result.message)
            self._btn_confirm.setEnabled(True)
            return

        self.completed = True
        self.accept()

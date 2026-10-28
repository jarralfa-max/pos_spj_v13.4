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

AUDITORÍA V03 (2026-10-15): el avance vivía sólo en memoria. Si un pago fallaba
a la mitad y se cerraba la ventana, la venta quedaba en cobro con pagos ya
guardados y el siguiente F9 abría un cobro en ceros que no podía iniciar. Ahora
el diálogo arranca DESDE LA VENTA: retoma su cobro, muestra los pagos ya
registrados y el saldo real, y permite quitar uno ya registrado (se anula y se
compensa: CxC, vale; el diálogo dice qué devolver al cliente). "Cerrar" sólo
cierra la ventana; sin pagos, la venta regresa al carrito.

"Pago mixto" no es un método: es lo que una venta es cuando registra dos
métodos distintos (`Sale.is_mixed_payment`). Mercado Pago registra un pago YA
confirmado (folio como referencia); la liga de cobro es de Pagos (§35).
"""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import (
    QComboBox, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,QWidget,
)
from frontend.desktop.components import (
    MoneyInput,
    StandardLineEdit,
    create_danger_button,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.dialogs import MessageDialog, StandardDialog

METHOD_LABELS = {
    "CASH": "Efectivo",
    "CARD": "Tarjeta",
    "TRANSFER": "Transferencia",
    "CREDIT": "Crédito",
    "MERCADO_PAGO": "Mercado Pago",
    "VOUCHER": "Vale / saldo a favor",
}


class PaymentDialog(StandardDialog):
    from PyQt5.QtCore import pyqtSignal
    public_state_changed = pyqtSignal(str)
    def __init__(self, presenter, *, sale_id: str, total_due: Decimal,
                 has_customer: bool = False, parent=None) -> None:
        super().__init__(parent, title="Cobrar", width=640)
        self.setObjectName("posPaymentDialog")
        self.setModal(True)
        self._presenter = presenter
        self._sale_id = sale_id
        self._total_due = Decimal(str(total_due))
        self._lines: list[tuple[str, Decimal, str | None]] = []
        #: Id del pago en la venta para cada línea ya registrada (None: local).
        self._payment_ids: list[str | None] = []
        self.completed = False
        self.change = Decimal("0")
        #: Avance ya aplicado al backend (ver docstring del módulo).
        self._checkout_started = False
        self._recorded = 0

        root = self.content_layout()

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

        add_row = QGridLayout()
        add_row.setColumnStretch(0, 1)
        add_row.setColumnStretch(1, 1)
        self._method = QComboBox(self)
        self._method.setObjectName("posPaymentMethod")
        for code in presenter.payment_methods(has_customer=has_customer):
            self._method.addItem(METHOD_LABELS.get(code, code), code)
        add_row.addWidget(self._method, 0, 0)

        self._amount = MoneyInput(self)
        self._amount.setObjectName("posPaymentAmount")
        add_row.addWidget(self._amount, 0, 1)

        self._reference = StandardLineEdit(self, placeholder="Referencia (opcional)")
        add_row.addWidget(self._reference, 1, 0)

        self._btn_add = create_secondary_button(self, "Agregar pago")
        self._btn_add.clicked.connect(self._add_line)
        add_row.addWidget(self._btn_add, 1, 1)
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

        footer = QWidget(self)
        actions = QHBoxLayout(footer)
        actions.setContentsMargins(0, 0, 0, 0)
        # "Cerrar" cierra la ventana; cancelar la VENTA es F8 (auditoría V03).
        btn_cancel = create_secondary_button(self, "Cerrar")
        btn_cancel.clicked.connect(self.reject)
        actions.addWidget(btn_cancel)

        self._btn_confirm = create_primary_button(self, "Confirmar y cobrar")
        self._btn_confirm.setObjectName("posPaymentConfirm")
        self._btn_confirm.setProperty("emphasis", "dominant")
        self._btn_confirm.clicked.connect(self._confirm)
        actions.addWidget(self._btn_confirm, stretch=1)
        self.add_footer_widget(footer)

        self._method.currentIndexChanged.connect(self._on_method_changed)
        self._load_persisted()
        self._on_method_changed()
        self._refresh_remaining()

    def _load_persisted(self) -> None:
        """Retoma un cobro ya iniciado: sus pagos guardados cuentan."""
        get_sale = getattr(self._presenter, "get_sale", None)
        sale = get_sale(self._sale_id) if callable(get_sale) else None
        if sale is None or sale.status not in ("CHECKOUT_PENDING", "PAYMENT_PENDING"):
            return
        self._checkout_started = True
        for payment in sale.payments:
            self._append_line(payment.method, Decimal(str(payment.amount)),
                              payment.reference, payment_id=payment.id)
        self._recorded = len(self._lines)
        if self._lines:
            self._show_hint(f"Cobro retomado: ya hay ${self._recorded_total():,.2f} "
                            "registrados en esta venta.")

    def _append_line(self, method: str, amount: Decimal, reference: str | None, *,
                     payment_id: str | None = None) -> None:
        self._lines.append((method, amount, reference))
        self._payment_ids.append(payment_id)
        label = f"{METHOD_LABELS.get(method, method)}: ${amount:,.2f}"
        if reference:
            label += f" ({reference})"
        if payment_id:
            label += " — registrado"
        self._list.addItem(QListWidgetItem(label))

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

    def prefill_voucher(self, code: str) -> None:
        """El cajero escaneó un vale: método «Vale», su código en «Referencia» y lo
        que puede pagar, en lenguaje de cajero (nunca un id interno)."""
        indice = self._method.findData("VOUCHER")
        if indice < 0:
            self._show_hint("No tienes permiso para cobrar con vales.")
            return
        self._method.setCurrentIndex(indice)
        self._on_method_changed()
        self._reference.setText(code)
        saldo = self._presenter.voucher_balance(code)
        if not saldo:
            return
        if not saldo.get("found"):
            self._show_hint(saldo.get("reason") or "Vale no reconocido.")
            return
        partes = [f"Vale {saldo.get('folio') or ''}".strip(),
                  f"saldo ${Decimal(str(saldo.get('balance') or 0)):,.2f}"]
        reglas = saldo.get("rules")
        if reglas is not None:
            if reglas.max_percent_per_sale is not None:
                partes.append(f"hasta {reglas.max_percent_per_sale:g} % de esta venta")
            partes.append("un solo uso" if reglas.effective_max_redemptions == 1
                          else "varios usos")
        self._show_hint(" · ".join(partes))

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
                    self._show_hint(saldo.get("reason")
                                    or f"No existe un vale con el código {reference}.")
                    return
                if Decimal(str(saldo.get("balance") or 0)) <= 0:
                    self._show_hint("El vale no tiene saldo.")
                    return
                amount = min(amount, Decimal(str(saldo["balance"])))
        self._append_line(method, amount, reference)
        self._refresh_remaining()
        self._on_method_changed()

    def _remove_selected(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        if row < self._recorded:
            self._void_recorded(row)
            return
        self._list.takeItem(row)
        del self._lines[row]
        del self._payment_ids[row]
        self._refresh_remaining()

    def _void_recorded(self, row: int) -> None:
        """Anula un pago YA registrado en la venta (auditoría V02/V03)."""
        from frontend.desktop.modules.sales_pos.dialogs.cancel_sale_dialog import (
            CancelSaleDialog,
        )
        method, amount, _reference = self._lines[row]
        payment_id = self._payment_ids[row]
        dialog = CancelSaleDialog(
            title="Anular pago", ok_text="Anular pago", parent=self,
            message=(f"Se anulará el pago de {METHOD_LABELS.get(method, method)} por "
                     f"${amount:,.2f} que ya está registrado en la venta."))
        if not dialog.exec_() or not dialog.reason or not payment_id:
            return
        result = self._presenter.void_payment(
            sale_id=self._sale_id, payment_id=payment_id, reason=dialog.reason)
        if not result.success:
            MessageDialog.warning(self, "No se pudo anular el pago", result.message)
            return
        self._list.takeItem(row)
        del self._lines[row]
        del self._payment_ids[row]
        self._recorded -= 1
        self._refresh_remaining()
        self._on_method_changed()
        refund = result.data.get("refund") or {}
        if refund.get("text"):
            MessageDialog.information(self, "Pago anulado", refund["text"])

    def reject(self) -> None:
        """Cerrar sin pagos registrados regresa la venta al carrito; con pagos,
        la venta queda en cobro y F9 la retoma (auditoría V03)."""
        back = getattr(self._presenter, "return_to_cart", None)
        if self._checkout_started and self._recorded == 0 and not self.completed                 and callable(back):
            back(sale_id=self._sale_id)
        super().reject()

    # ── aplicación real, sólo al confirmar ───────────────────────────────
    def _confirm(self) -> None:
        self.public_state_changed.emit("PENDING")
        self._btn_confirm.setEnabled(False)

        if not self._checkout_started:
            checkout = self._presenter.begin_checkout(sale_id=self._sale_id)
            if not checkout.success:
                self.public_state_changed.emit("FAILED")
                MessageDialog.warning(self, "No se pudo iniciar el cobro", checkout.message)
                self._btn_confirm.setEnabled(True)
                return
            self._checkout_started = True

        while self._recorded < len(self._lines):
            method, amount, reference = self._lines[self._recorded]
            result = self._presenter.record_payment(
                sale_id=self._sale_id, method=method, amount=amount, reference=reference)
            if not result.success:
                self.public_state_changed.emit("FAILED")
                MessageDialog.warning(
                    self, "Pago no registrado",
                    f"{result.message}\n\nLos pagos ya registrados quedan aplicados a la venta: "
                    "corrige el pago restante, quita uno registrado con «Quitar pago "
                    "seleccionado», o cierra y cancela la venta con F8 (se anularán sus "
                    "pagos y verás qué devolver).")
                self._btn_confirm.setEnabled(True)
                return
            sale = result.data.get("sale")
            known = {pid for pid in self._payment_ids if pid}
            nuevos = [p.id for p in (sale.payments if sale is not None else ())
                      if p.id not in known]
            self._payment_ids[self._recorded] = nuevos[-1] if nuevos else None
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
            self.public_state_changed.emit("FAILED")
            MessageDialog.warning(self, "No se pudo finalizar la venta", result.message)
            self._btn_confirm.setEnabled(True)
            return

        self.completed = True
        self.accept()

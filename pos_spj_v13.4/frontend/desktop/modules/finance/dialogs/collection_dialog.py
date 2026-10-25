"""Cobro a cliente con aplicación EXPLÍCITA a sus documentos (§11).

Un cobro puede liquidar varias facturas, una parte o ninguna: lo que no se
aplica queda como saldo a favor del cliente (anticipo), visible y aplicable
después. El diálogo sólo suma con ``Decimal`` para avisar; el caso de uso
vuelve a validar saldos y moneda.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt5.QtWidgets import QComboBox, QLabel, QLineEdit, QTableWidget, QTableWidgetItem

from frontend.desktop.components.date_input import DateInput
from frontend.desktop.components.money_input import MoneyInput
from frontend.desktop.modules.finance.dialogs._form_dialog import FinanceFormDialog

PAYMENT_METHODS = [("BANK_TRANSFER", "Transferencia"), ("CASH", "Efectivo"),
                   ("CARD", "Tarjeta"), ("CHECK", "Cheque")]


class CollectionDialog(FinanceFormDialog):
    dialog_title = "Registrar cobro"

    def __init__(self, parent, *, customer_label: str, receivables: list[dict],
                 treasury_accounts: list[tuple[str, str]], preselected: str | None = None,
                 apply_only: bool = False, available: str | None = None) -> None:
        """``apply_only``: aplica un saldo a favor existente (sin dinero nuevo)."""
        self._customer_label = customer_label
        self._receivables = receivables
        self._treasury_accounts = treasury_accounts
        self._preselected = preselected
        self._apply_only = apply_only
        self._available = Decimal(available) if available else None
        if apply_only:
            self.dialog_title = "Aplicar saldo a favor"
        super().__init__(parent)
        self.setMinimumWidth(640)

    def _build_form(self) -> None:
        self.form.addRow("Cliente:", QLabel(self._customer_label, self))
        if not self._apply_only:
            self.amount_input = MoneyInput(self)
            self.amount_input.valueChanged.connect(self._refresh)
            self.account_combo = QComboBox(self)
            for account_id, name in self._treasury_accounts:
                self.account_combo.addItem(name, account_id)
            self.method_combo = QComboBox(self)
            for value, label in PAYMENT_METHODS:
                self.method_combo.addItem(label, value)
            self.date_input = DateInput(self)
            self.reference_input = QLineEdit(self)
            self.form.addRow("Importe recibido *:", self.amount_input)
            self.form.addRow("Cuenta que recibe *:", self.account_combo)
            self.form.addRow("Forma de pago:", self.method_combo)
            self.form.addRow("Fecha del cobro:", self.date_input)
            self.form.addRow("Referencia:", self.reference_input)
        else:
            self.form.addRow("Saldo a favor disponible:", QLabel(f"{self._available:,.2f}", self))
        self.table = QTableWidget(len(self._receivables), 3, self)
        self.table.setHorizontalHeaderLabels(["Documento", "Saldo", "Aplicar"])
        self.table.horizontalHeader().setStretchLastSection(True)
        for row, receivable in enumerate(self._receivables):
            self.table.setItem(row, 0, QTableWidgetItem(receivable["label"]))
            self.table.setItem(row, 1, QTableWidgetItem(receivable["outstanding"]))
            editor = QLineEdit(self.table)
            editor.setPlaceholderText("0.00")
            if receivable["id"] == self._preselected:
                editor.setText(receivable["outstanding"])
            editor.textChanged.connect(self._refresh)
            self.table.setCellWidget(row, 2, editor)
        self.table.setMinimumHeight(160)
        self.form.addRow(self.table)
        self.summary_label = QLabel("", self)
        self.summary_label.setProperty("role", "muted")
        self.form.addRow(self.summary_label)
        if not self._apply_only and self._preselected:
            for receivable in self._receivables:
                if receivable["id"] == self._preselected:
                    self.amount_input.set_decimal_value(receivable["outstanding"])
        self._refresh()

    def _applied(self) -> list[tuple[dict, Decimal]]:
        result = []
        for row, receivable in enumerate(self._receivables):
            text = self.table.cellWidget(row, 2).text().strip()
            if text:
                result.append((receivable, Decimal(text)))
        return result

    def _total(self) -> Decimal:
        if self._apply_only:
            return self._available or Decimal("0")
        return self.amount_input.decimal_value()

    def _refresh(self, *_args) -> None:
        try:
            applied = sum((amount for _, amount in self._applied()), Decimal("0"))
        except InvalidOperation:
            self.summary_label.setText("Hay un importe a aplicar inválido.")
            return
        remaining = self._total() - applied
        self.summary_label.setText(f"Aplicado {applied:,.2f} · queda a favor {remaining:,.2f}")

    def _validation_error(self) -> str | None:
        if not self._apply_only:
            if not self.account_combo.currentData():
                return "Elija la cuenta de tesorería que recibe el cobro."
            if self.amount_input.decimal_value() <= 0:
                return "El importe del cobro debe ser mayor que cero."
        try:
            applied = self._applied()
        except InvalidOperation:
            return "Hay un importe a aplicar inválido."
        for receivable, amount in applied:
            if amount <= 0:
                return f"{receivable['label']}: lo aplicado debe ser mayor que cero."
            if amount > Decimal(receivable["outstanding"]):
                return f"{receivable['label']}: lo aplicado excede su saldo."
        if sum((a for _, a in applied), Decimal("0")) > self._total():
            return "Lo aplicado excede el importe disponible."
        if self._apply_only and not applied:
            return "Capture cuánto aplicar a cada documento."
        return None

    def applications(self) -> list[dict]:
        return [{"receivable_id": r["id"], "amount": format(a, "f")} for r, a in self._applied()]

    def data(self) -> dict:
        return {
            "amount": format(self.amount_input.decimal_value(), "f"),
            "treasury_account_id": self.account_combo.currentData(),
            "payment_method": self.method_combo.currentData(),
            "collection_date": self.date_input.date_value(),
            "reference": self.reference_input.text().strip(),
            "applications": self.applications(),
        }

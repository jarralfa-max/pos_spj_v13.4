"""Diálogo de programación de pago a proveedor."""

from __future__ import annotations

from datetime import date

from PyQt5.QtCore import QDate
from PyQt5.QtWidgets import QComboBox, QDateEdit, QLineEdit

from frontend.desktop.components.money_input import MoneyInput
from frontend.desktop.modules.finance.dialogs._form_dialog import FinanceFormDialog


class SupplierPaymentDialog(FinanceFormDialog):
    dialog_title = "Programar pago a proveedor"

    def __init__(self, parent, treasury_accounts: list[tuple[str, str]]) -> None:
        self._treasury_accounts = treasury_accounts
        super().__init__(parent)

    def _build_form(self) -> None:
        self.amount_input = MoneyInput(self)
        self.account_combo = QComboBox(self)
        for account_id, name in self._treasury_accounts:
            self.account_combo.addItem(name, account_id)
        self.date_input = QDateEdit(QDate.currentDate(), self)
        self.date_input.setCalendarPopup(True)
        self.reference_input = QLineEdit(self)
        self.form.addRow("Importe:", self.amount_input)
        self.form.addRow("Origen de fondos:", self.account_combo)
        self.form.addRow("Fecha programada:", self.date_input)
        self.form.addRow("Referencia:", self.reference_input)

    def _is_valid(self) -> bool:
        return self.amount_input.decimal_value() > 0 and self.account_combo.currentData()

    def data(self) -> dict:
        qdate = self.date_input.date()
        return {
            "amount": str(self.amount_input.decimal_value()),
            "treasury_account_id": self.account_combo.currentData(),
            "scheduled_date": date(qdate.year(), qdate.month(), qdate.day()),
            "reference": self.reference_input.text().strip(),
        }

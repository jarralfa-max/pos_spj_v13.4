"""Diálogo de solicitud de gasto (compromiso presupuestal)."""

from __future__ import annotations

from PyQt5.QtWidgets import QComboBox

from frontend.desktop.components.money_input import MoneyInput
from frontend.desktop.modules.finance.dialogs._form_dialog import FinanceFormDialog


class ExpenseRequestDialog(FinanceFormDialog):
    dialog_title = "Solicitud de gasto"

    def __init__(self, parent, expense_accounts: list[tuple[str, str]]) -> None:
        self._expense_accounts = expense_accounts
        super().__init__(parent)

    def _build_form(self) -> None:
        self.account_combo = QComboBox(self)
        for account_id, label in self._expense_accounts:
            self.account_combo.addItem(label, account_id)
        self.amount_input = MoneyInput(self)
        self.form.addRow("Cuenta de gasto:", self.account_combo)
        self.form.addRow("Importe:", self.amount_input)

    def _is_valid(self) -> bool:
        return self.amount_input.decimal_value() > 0 and self.account_combo.currentData()

    def data(self) -> dict:
        return {
            "account_id": self.account_combo.currentData(),
            "amount": str(self.amount_input.decimal_value()),
        }

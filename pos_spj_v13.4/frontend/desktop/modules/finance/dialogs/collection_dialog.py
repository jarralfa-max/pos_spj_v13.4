"""Diálogo de cobro de CxC."""

from __future__ import annotations

from PyQt5.QtWidgets import QComboBox, QLineEdit

from frontend.desktop.components.money_input import MoneyInput
from frontend.desktop.modules.finance.dialogs._form_dialog import FinanceFormDialog


class CollectionDialog(FinanceFormDialog):
    dialog_title = "Registrar cobro"

    def __init__(self, parent, treasury_accounts: list[tuple[str, str]]) -> None:
        self._treasury_accounts = treasury_accounts
        super().__init__(parent)

    def _build_form(self) -> None:
        self.amount_input = MoneyInput(self)
        self.account_combo = QComboBox(self)
        for account_id, name in self._treasury_accounts:
            self.account_combo.addItem(name, account_id)
        self.reference_input = QLineEdit(self)
        self.form.addRow("Importe:", self.amount_input)
        self.form.addRow("Cuenta de tesorería:", self.account_combo)
        self.form.addRow("Referencia:", self.reference_input)

    def _is_valid(self) -> bool:
        return self.amount_input.decimal_value() > 0 and self.account_combo.currentData()

    def data(self) -> dict:
        return {
            "amount": str(self.amount_input.decimal_value()),
            "treasury_account_id": self.account_combo.currentData(),
            "reference": self.reference_input.text().strip(),
        }

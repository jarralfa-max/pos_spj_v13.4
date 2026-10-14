"""Diálogo de transferencia entre cuentas de tesorería."""

from __future__ import annotations

from PyQt5.QtWidgets import QComboBox, QLineEdit

from frontend.desktop.components.money_input import MoneyInput
from frontend.desktop.modules.finance.dialogs._form_dialog import FinanceFormDialog


class BankTransferDialog(FinanceFormDialog):
    dialog_title = "Transferencia de tesorería"

    def __init__(self, parent, treasury_accounts: list[tuple[str, str]]) -> None:
        self._treasury_accounts = treasury_accounts
        super().__init__(parent)

    def _build_form(self) -> None:
        self.source_combo = QComboBox(self)
        self.target_combo = QComboBox(self)
        for account_id, name in self._treasury_accounts:
            self.source_combo.addItem(name, account_id)
            self.target_combo.addItem(name, account_id)
        self.amount_input = MoneyInput(self)
        self.reference_input = QLineEdit(self)
        self.form.addRow("Cuenta origen:", self.source_combo)
        self.form.addRow("Cuenta destino:", self.target_combo)
        self.form.addRow("Importe:", self.amount_input)
        self.form.addRow("Referencia:", self.reference_input)

    def _validation_error(self) -> str | None:
        if not self.source_combo.currentData() or not self.target_combo.currentData():
            return "Elija la cuenta de origen y la de destino."
        if self.source_combo.currentData() == self.target_combo.currentData():
            return "El origen y el destino deben ser cuentas distintas."
        if self.amount_input.decimal_value() <= 0:
            return "El importe debe ser mayor que cero."
        return None

    def _is_valid(self) -> bool:
        return self._validation_error() is None

    def data(self) -> dict:
        return {
            "source_id": self.source_combo.currentData(),
            "target_id": self.target_combo.currentData(),
            "amount": str(self.amount_input.decimal_value()),
            "reference": self.reference_input.text().strip(),
        }

"""Diálogo de alta de presupuesto (una línea inicial)."""

from __future__ import annotations

from datetime import date

from PyQt5.QtWidgets import QComboBox, QLineEdit, QSpinBox

from frontend.desktop.components.money_input import MoneyInput
from frontend.desktop.modules.finance.dialogs._form_dialog import FinanceFormDialog


class BudgetDialog(FinanceFormDialog):
    dialog_title = "Nuevo presupuesto"

    def __init__(self, parent, expense_accounts: list[tuple[str, str]]) -> None:
        self._expense_accounts = expense_accounts
        super().__init__(parent)

    def _build_form(self) -> None:
        self.name_input = QLineEdit(self)
        self.year_input = QSpinBox(self)
        self.year_input.setRange(2020, 2100)
        self.year_input.setValue(date.today().year)
        self.account_combo = QComboBox(self)
        for account_id, label in self._expense_accounts:
            self.account_combo.addItem(label, account_id)
        self.amount_input = MoneyInput(self)
        self.form.addRow("Nombre:", self.name_input)
        self.form.addRow("Año fiscal:", self.year_input)
        self.form.addRow("Cuenta:", self.account_combo)
        self.form.addRow("Importe del periodo actual:", self.amount_input)

    def _is_valid(self) -> bool:
        return bool(self.name_input.text().strip()) and self.amount_input.decimal_value() > 0

    def data(self) -> dict:
        today = date.today()
        return {
            "name": self.name_input.text().strip(),
            "fiscal_year": self.year_input.value(),
            "lines": [{
                "account_id": self.account_combo.currentData(),
                "period_code": f"{today.year:04d}-{today.month:02d}",
                "planned_amount": str(self.amount_input.decimal_value()),
            }],
        }

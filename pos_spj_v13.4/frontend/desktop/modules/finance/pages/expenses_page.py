"""Solicitudes de gasto contra presupuesto."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage
from modulos.ui_components import create_primary_button


class ExpensesPage(FinancePage):
    title = "Gastos"
    subtitle = "Compromiso presupuestal previo al gasto"
    columns = [
        ColumnSpec("Presupuesto"),
        ColumnSpec("Año", "date"),
        ColumnSpec("Versión", "date"),
        ColumnSpec("Estado", "status"),
        ColumnSpec("Aprobó", "date"),
    ]

    def _build_actions(self) -> None:
        request_btn = create_primary_button(self, "Solicitar gasto")
        request_btn.clicked.connect(self._request)
        self.header.add_action(request_btn)

    def _request(self) -> None:
        from frontend.desktop.modules.finance.dialogs.expense_request_dialog import (
            ExpenseRequestDialog,
        )
        dialog = ExpenseRequestDialog(self, self._presenter.postable_expense_accounts())
        if dialog.exec_():
            data = dialog.data()
            self.notify(*self._presenter.register_expense_request(**data))

    def _load(self) -> None:
        self.set_table(self._presenter.budgets())

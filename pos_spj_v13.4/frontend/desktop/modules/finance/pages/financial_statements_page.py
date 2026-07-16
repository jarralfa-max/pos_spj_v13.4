"""Estados financieros — balanza, balance, resultados y flujo."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.finance.finance_view_models import money_display
from frontend.desktop.modules.finance.pages._page_base import FinancePage


class FinancialStatementsPage(FinancePage):
    title = "Estados financieros"
    subtitle = "Balanza, balance general, resultados y flujo de efectivo"
    columns = [
        ColumnSpec("Código", "date"),
        ColumnSpec("Cuenta"),
        ColumnSpec("Tipo", "status"),
        ColumnSpec("Debe", "numeric"),
        ColumnSpec("Haber", "numeric"),
        ColumnSpec("Saldo", "numeric"),
    ]

    def _build_extra(self) -> None:
        self._summary = StandardTable(
            [ColumnSpec("Concepto"), ColumnSpec("Importe", "numeric")], self)
        self._summary.setMaximumHeight(280)
        self._layout.addWidget(self._summary)

    def _load(self) -> None:
        self.set_table(self._presenter.trial_balance())
        income = self._presenter.income_statement()
        balance = self._presenter.balance_sheet()
        cash_flow = self._presenter.cash_flow_statement()
        rows = [
            ["Ingresos netos", money_display(income["net_revenue"])],
            ["Costo de ventas", money_display(income["cost_of_sales"])],
            ["Utilidad bruta", money_display(income["gross_profit"])],
            ["Gastos de operación", money_display(income["operating_expenses"])],
            ["Utilidad neta", money_display(income["net_income"])],
            ["Activos", money_display(balance["assets"])],
            ["Pasivos", money_display(balance["liabilities"])],
            ["Capital (incl. resultado)", money_display(balance["equity_total"])],
            ["Flujo operativo", money_display(cash_flow["operating"])],
            ["Flujo de inversión", money_display(cash_flow["investing"])],
            ["Flujo de financiamiento", money_display(cash_flow["financing"])],
        ]
        self._summary.load_rows(rows)

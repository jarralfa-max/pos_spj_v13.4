"""Estados financieros (§31) desde asientos contabilizados: resultados,
balance general, flujo de efectivo (método directo), cambios en el capital y
comparativo contra el periodo anterior de igual duración."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.components.tabs import Tabs
from frontend.desktop.modules.finance.pages._page_base import FinancePage

_INCOME = [("revenue", "Ingresos"), ("contra_revenue", "Devoluciones y descuentos"),
           ("net_revenue", "Ingresos netos"), ("cost_of_sales", "Costo de ventas"),
           ("gross_profit", "Utilidad bruta"), ("operating_expenses", "Gastos de operación"),
           ("operating_income", "Utilidad de operación"), ("other_income", "Otros ingresos"),
           ("other_expense", "Otros gastos"), ("income_before_taxes", "Utilidad antes de impuestos"),
           ("income_taxes", "Impuestos a la utilidad"), ("net_income", "Utilidad neta")]
_BALANCE = [("assets", "Activos"), ("liabilities", "Pasivos"), ("equity", "Capital contable"),
            ("period_net_income", "Resultado del ejercicio"),
            ("equity_total", "Capital total (incl. resultado)")]
_CASH = [("opening_cash", "Efectivo inicial"), ("operating", "Flujo de operación"),
         ("investing", "Flujo de inversión"), ("financing", "Flujo de financiamiento"),
         ("net_change_in_cash", "Variación neta"), ("closing_cash", "Efectivo final")]
_EQUITY = [("opening_equity", "Capital inicial"), ("change", "Variación"),
           ("closing_equity", "Capital final")]


def _summary_table(parent) -> StandardTable:
    return StandardTable([ColumnSpec("Concepto"), ColumnSpec("Importe", "numeric")], parent)


def _detail_table(parent) -> StandardTable:
    return StandardTable([ColumnSpec("Cuenta"), ColumnSpec("Nombre"),
                          ColumnSpec("Saldo", "numeric")], parent)


class FinancialStatementsPage(FinancePage):
    title = "Estados financieros"
    subtitle = "Generados de asientos contabilizados, en moneda base"
    period_filter = True
    exportable = False

    def _build_extra(self) -> None:
        self._tabs = Tabs(self)
        self._income, self._income_detail = _summary_table(self), _detail_table(self)
        self._balance, self._balance_detail = _summary_table(self), _detail_table(self)
        self._cash = _summary_table(self)
        self._equity = _summary_table(self)
        self._comparative = StandardTable([
            ColumnSpec("Concepto"), ColumnSpec("Periodo", "numeric"),
            ColumnSpec("Anterior", "numeric"), ColumnSpec("Variación", "numeric"),
            ColumnSpec("%", "numeric")], self)
        self._tabs.addTab(self._income, "Resultados")
        self._tabs.addTab(self._income_detail, "Resultados por cuenta")
        self._tabs.addTab(self._balance, "Balance general")
        self._tabs.addTab(self._balance_detail, "Balance por cuenta")
        self._tabs.addTab(self._cash, "Flujo de efectivo")
        self._tabs.addTab(self._equity, "Cambios en el capital")
        self._tabs.addTab(self._comparative, "Comparativo")
        self._layout.addWidget(self._tabs, stretch=1)

    def _load(self) -> None:
        p = self._presenter
        date_from, date_to = self.period()
        data = p.statements(date_from, date_to)
        self._income.load_rows(p.statement_table(data["income"], _INCOME).rows)
        self._income_detail.load_rows(p.statement_detail(data["income"]).rows)
        self._balance.load_rows(p.statement_table(data["balance"], _BALANCE).rows)
        self._balance_detail.load_rows(p.statement_detail(data["balance"]).rows)
        self._cash.load_rows(p.statement_table(data["cash_flow"], _CASH).rows)
        self._equity.load_rows(p.statement_table(data["equity"], _EQUITY).rows)
        labels = dict(_INCOME)
        comparative = p.comparative_income(date_from, date_to)
        self._comparative.load_rows([[labels.get(r[0], r[0]), *r[1:]]
                                     for r in comparative.rows])

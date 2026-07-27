"""FinanceView — main finance module view (navigation + lazy pages).

The view receives a fully wired ``FinancePresenter``; it never touches the
database, the app container, SQL or business rules. Validated at 1366×768.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.modules.finance.pages.accounts_payable_page import AccountsPayablePage
from frontend.desktop.modules.finance.pages.accounts_receivable_page import (
    AccountsReceivablePage,
)
from frontend.desktop.modules.finance.pages.bank_reconciliation_page import (
    BankReconciliationPage,
)
from frontend.desktop.modules.finance.pages.budgets_page import BudgetsPage
from frontend.desktop.modules.finance.pages.capital_page import CapitalPage
from frontend.desktop.modules.finance.pages.chart_of_accounts_page import ChartOfAccountsPage
from frontend.desktop.modules.finance.pages.collections_page import CollectionsPage
from frontend.desktop.modules.finance.pages.commercial_instruments_page import (
    CommercialInstrumentsPage,
)
from frontend.desktop.modules.finance.pages.expenses_page import ExpensesPage
from frontend.desktop.modules.finance.pages.finance_settings_page import FinanceSettingsPage
from frontend.desktop.modules.finance.pages.financial_statements_page import (
    FinancialStatementsPage,
)
from frontend.desktop.modules.finance.pages.fiscal_periods_page import FiscalPeriodsPage
from frontend.desktop.modules.finance.pages.fixed_assets_page import FixedAssetsPage
from frontend.desktop.modules.finance.pages.general_ledger_page import GeneralLedgerPage
from frontend.desktop.modules.finance.pages.journal_entries_page import JournalEntriesPage
from frontend.desktop.modules.finance.pages.overview_page import OverviewPage
from frontend.desktop.modules.finance.pages.payments_page import PaymentsPage
from frontend.desktop.modules.finance.pages.treasury_page import TreasuryPage

#: (section label or None, page label, page class) — §25 navigation
_NAVIGATION = [
    (None, "Resumen financiero", OverviewPage),
    ("Contabilidad", "Plan de cuentas", ChartOfAccountsPage),
    ("Contabilidad", "Asientos", JournalEntriesPage),
    ("Contabilidad", "Libro mayor", GeneralLedgerPage),
    ("Contabilidad", "Periodos", FiscalPeriodsPage),
    ("Cobranza", "Cuentas por cobrar", AccountsReceivablePage),
    ("Cobranza", "Cobros", CollectionsPage),
    ("Pagos", "Cuentas por pagar", AccountsPayablePage),
    ("Pagos", "Programación y autorizaciones", PaymentsPage),
    ("Tesorería", "Cuentas y transferencias", TreasuryPage),
    ("Tesorería", "Conciliación", BankReconciliationPage),
    ("Planeación financiera", "Presupuestos", BudgetsPage),
    ("Planeación financiera", "Gastos", ExpensesPage),
    ("Planeación financiera", "Capital y CAPEX", CapitalPage),
    ("Activos", "Registro y depreciación", FixedAssetsPage),
    ("Instrumentos comerciales", "Obligaciones y conciliación", CommercialInstrumentsPage),
    ("Estados financieros", "Balanza, balance, resultados y flujo", FinancialStatementsPage),
    (None, "Configuración", FinanceSettingsPage),
]


class FinanceView(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self.setObjectName("financeModule")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._nav = QListWidget(self)
        self._nav.setObjectName("financeNav")
        self._nav.setMaximumWidth(260)
        self._nav.setMinimumWidth(220)

        self._stack = QStackedWidget(self)
        self._pages: list = []
        self._build_navigation()

        layout.addWidget(self._nav)
        content = QWidget(self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self._stack)
        layout.addWidget(content, stretch=1)

        self._nav.currentRowChanged.connect(self._on_nav_changed)
        self._nav.setCurrentRow(self._first_page_row)

    def _build_navigation(self) -> None:
        current_section = object()
        self._row_to_page_index: dict[int, int] = {}
        self._first_page_row = 0
        first_set = False
        for section, label, page_class in _NAVIGATION:
            if section is not None and section != current_section:
                header_item = QListWidgetItem(section.upper())
                header_item.setFlags(Qt.NoItemFlags)
                self._nav.addItem(header_item)
            current_section = section if section is not None else current_section
            item = QListWidgetItem(f"  {label}")
            self._nav.addItem(item)
            page = page_class(self._presenter, self)
            self._stack.addWidget(page)
            self._pages.append(page)
            row = self._nav.count() - 1
            self._row_to_page_index[row] = len(self._pages) - 1
            if not first_set:
                self._first_page_row = row
                first_set = True

    def _on_nav_changed(self, row: int) -> None:
        page_index = self._row_to_page_index.get(row)
        if page_index is None:
            return
        self._stack.setCurrentIndex(page_index)
        self._pages[page_index].ensure_loaded()

    def set_active_submodule(self, name: str) -> None:
        """Compatibility hook (e.g. legacy 'tesoreria' deep link)."""
        targets = {"tesoreria": TreasuryPage, "cxc": AccountsReceivablePage,
                   "cxp": AccountsPayablePage}
        page_class = targets.get(str(name or "").lower())
        if page_class is None:
            return
        for index, page in enumerate(self._pages):
            if isinstance(page, page_class):
                for row, mapped in self._row_to_page_index.items():
                    if mapped == index:
                        self._nav.setCurrentRow(row)
                        return

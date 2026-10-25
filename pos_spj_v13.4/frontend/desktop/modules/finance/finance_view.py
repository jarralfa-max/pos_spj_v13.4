"""FinanceView — vista principal de Finanzas (navegación §29 + páginas).

Recibe un ``FinancePresenter`` ya compuesto; nunca toca la base, el
contenedor, SQL ni reglas de negocio. Validada a 1366×768.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QWidget

from frontend.desktop.components.icons import Icons
from frontend.desktop.components.module_layout import ModuleLayout
from frontend.desktop.components.page_stack import PageStack
from frontend.desktop.components.side_nav import SideNav
from frontend.desktop.modules.finance.pages.accounts_payable_page import AccountsPayablePage
from frontend.desktop.modules.finance.pages.accounts_receivable_page import (
    AccountsReceivablePage,
)
from frontend.desktop.modules.finance.pages.aging_page import AgingPage
from frontend.desktop.modules.finance.pages.audit_log_page import AuditLogPage
from frontend.desktop.modules.finance.pages.bank_reconciliation_page import (
    BankReconciliationPage,
)
from frontend.desktop.modules.finance.pages.budgets_page import BudgetsPage
from frontend.desktop.modules.finance.pages.capital_page import CapitalPage
from frontend.desktop.modules.finance.pages.cash_projection_page import CashProjectionPage
from frontend.desktop.modules.finance.pages.chart_of_accounts_page import ChartOfAccountsPage
from frontend.desktop.modules.finance.pages.collections_page import CollectionsPage
from frontend.desktop.modules.finance.pages.commercial_instruments_page import (
    CommercialInstrumentsPage,
)
from frontend.desktop.modules.finance.pages.currencies_page import CurrenciesPage
from frontend.desktop.modules.finance.pages.depreciation_page import DepreciationPage
from frontend.desktop.modules.finance.pages.dimensions_page import DimensionsPage
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
from frontend.desktop.modules.finance.pages.posting_profiles_page import PostingProfilesPage
from frontend.desktop.modules.finance.pages.profitability_page import ProfitabilityPage
from frontend.desktop.modules.finance.pages.suppliers_page import SuppliersPage
from frontend.desktop.modules.finance.pages.taxes_page import TaxesPage
from frontend.desktop.modules.finance.pages.treasury_movements_page import (
    TreasuryMovementsPage,
)
from frontend.desktop.modules.finance.pages.treasury_page import TreasuryPage
from frontend.desktop.modules.finance.pages.trial_balance_page import TrialBalancePage

#: (sección o None, etiqueta, clase de página, ícono) — navegación §29.1
_NAVIGATION = [
    (None, "Resumen", OverviewPage, Icons.DASHBOARD),
    ("Contabilidad", "Plan de cuentas", ChartOfAccountsPage, Icons.CATALOG),
    ("Contabilidad", "Asientos", JournalEntriesPage, Icons.EDIT),
    ("Contabilidad", "Libro mayor", GeneralLedgerPage, Icons.LIST),
    ("Contabilidad", "Balanza", TrialBalancePage, Icons.REPORT),
    ("Contabilidad", "Periodos y cierre", FiscalPeriodsPage, Icons.CALENDAR),
    ("Cobranza", "Cuentas por cobrar", AccountsReceivablePage, Icons.CUSTOMERS),
    ("Cobranza", "Cobros", CollectionsPage, Icons.IMPORT),
    ("Pagos", "Cuentas por pagar", AccountsPayablePage, Icons.RECEIPT),
    ("Pagos", "Programación y autorizaciones", PaymentsPage, Icons.EXPORT),
    ("Proveedores", "Maestro de proveedores", SuppliersPage, Icons.SUPPLIER),
    ("Tesorería", "Cuentas", TreasuryPage, Icons.TRANSFERS),
    ("Tesorería", "Movimientos", TreasuryMovementsPage, Icons.LIST),
    ("Tesorería", "Conciliación", BankReconciliationPage, Icons.CHECK),
    ("Planeación", "Presupuestos", BudgetsPage, Icons.FORECAST),
    ("Planeación", "Gastos", ExpensesPage, Icons.CASH),
    ("Planeación", "Capital y préstamos", CapitalPage, Icons.FINANCE),
    ("Planeación", "Proyección de flujo", CashProjectionPage, Icons.CHART),
    ("Activos", "Activos fijos", FixedAssetsPage, Icons.ASSETS),
    ("Activos", "Depreciación", DepreciationPage, Icons.CALENDAR),
    ("Instrumentos comerciales", "Obligaciones", CommercialInstrumentsPage, Icons.DOCUMENT),
    ("Análisis", "Estados financieros", FinancialStatementsPage, Icons.REPORT),
    ("Análisis", "Rentabilidad", ProfitabilityPage, Icons.CHART),
    ("Análisis", "Antigüedad de saldos", AgingPage, Icons.CALENDAR),
    ("Configuración", "Parámetros", FinanceSettingsPage, Icons.SETTINGS),
    ("Configuración", "Perfiles contables", PostingProfilesPage, Icons.CATALOG),
    ("Configuración", "Impuestos", TaxesPage, Icons.RECEIPT),
    ("Configuración", "Monedas", CurrenciesPage, Icons.CASH),
    ("Configuración", "Dimensiones", DimensionsPage, Icons.LIST),
    ("Configuración", "Auditoría", AuditLogPage, Icons.CHECK),
]

_GROUP_ICONS = {
    "Contabilidad": Icons.FINANCE, "Cobranza": Icons.CASH, "Pagos": Icons.EXPORT,
    "Proveedores": Icons.SUPPLIER, "Tesorería": Icons.TRANSFERS,
    "Planeación": Icons.FORECAST, "Activos": Icons.ASSETS,
    "Instrumentos comerciales": Icons.DOCUMENT, "Análisis": Icons.CHART,
    "Configuración": Icons.SETTINGS,
}

#: Rutas de alertas y enlaces profundos → página que las atiende.
_ROUTES = {
    "periods": FiscalPeriodsPage, "journal": JournalEntriesPage,
    "reconciliation": BankReconciliationPage, "treasury": TreasuryPage,
    "tesoreria": TreasuryPage, "receivables": AccountsReceivablePage,
    "cxc": AccountsReceivablePage, "payables": AccountsPayablePage,
    "cxp": AccountsPayablePage, "payments": PaymentsPage, "budgets": BudgetsPage,
    "proveedores": SuppliersPage,
}


class FinanceView(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self.setObjectName("financeModule")

        self._nav = SideNav(self)
        self._nav.setObjectName("financeNav")

        self._stack = PageStack(self)
        self._pages: list = []
        self._build_navigation()

        self.module_layout = ModuleLayout(
            self, title="Finanzas", icon=Icons.FINANCE,
            sidebar=self._nav, content=self._stack,
        )

        self._nav.navigated.connect(self._on_nav_changed)
        self._nav.setCurrentRow(self._first_page_row)

    def _build_navigation(self) -> None:
        current_section = object()
        self._row_to_page_index: dict[int, int] = {}
        self._first_page_row = 0
        first_set = False
        for section, label, page_class, icon in _NAVIGATION:
            if section is not None and section != current_section:
                self._nav.add_group(section.upper(), icon=_GROUP_ICONS[section])
            current_section = section if section is not None else current_section
            self._nav.add_section(label.strip(), icon=icon)
            page = page_class(self._presenter, self)
            if isinstance(page, OverviewPage):
                page.navigate_requested.connect(self.open_route)
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

    def open_route(self, route: str) -> None:
        """Lleva a la sección que atiende una alerta o un enlace profundo."""
        page_class = _ROUTES.get(str(route or "").lower())
        if page_class is None:
            return
        for index, page in enumerate(self._pages):
            if isinstance(page, page_class):
                for row, mapped in self._row_to_page_index.items():
                    if mapped == index:
                        self._nav.setCurrentRow(row)
                        return

    def set_active_submodule(self, name: str) -> None:
        """Enlace profundo heredado (p. ej. 'tesoreria')."""
        self.open_route(name)

    def aplicar_contexto(self, context: dict) -> None:
        """CRM-37 (NavigationIntent ``"finance.receivables"``): Cliente 360 llega
        con el cliente ya resuelto; abre CxC filtrada y muestra su exposición."""
        customer_id = str((context or {}).get("customer_id")
                          or (context or {}).get("legacy_customer_id") or "").strip()
        if not customer_id:
            return
        self.open_route("cxc")
        for page in self._pages:
            if isinstance(page, AccountsReceivablePage):
                page.show_crm_summary_for(customer_id)
                return

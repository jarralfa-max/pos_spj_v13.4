"""Plan de cuentas."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage


class ChartOfAccountsPage(FinancePage):
    title = "Plan de cuentas"
    subtitle = "Catálogo contable canónico"
    columns = [
        ColumnSpec("Código", "date"),
        ColumnSpec("Nombre"),
        ColumnSpec("Tipo", "status"),
        ColumnSpec("Posteable", "status"),
        ColumnSpec("Estado", "status"),
    ]

    def _load(self) -> None:
        self.set_table(self._presenter.chart_of_accounts())

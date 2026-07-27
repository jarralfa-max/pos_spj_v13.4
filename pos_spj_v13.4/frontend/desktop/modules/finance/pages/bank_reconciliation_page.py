"""Conciliación bancaria."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage


class BankReconciliationPage(FinancePage):
    title = "Conciliación bancaria"
    subtitle = "Estados importados y matching contra el libro mayor"
    columns = [
        ColumnSpec("Cuenta de tesorería"),
        ColumnSpec("Estado", "status"),
        ColumnSpec("Completó", "date"),
        ColumnSpec("Fecha", "date"),
    ]

    def _load(self) -> None:
        self.set_table(self._presenter.reconciliations())

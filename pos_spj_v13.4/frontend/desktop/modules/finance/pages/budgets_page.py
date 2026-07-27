"""Presupuestos y ejecución."""

from __future__ import annotations

from datetime import date

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage


class BudgetsPage(FinancePage):
    title = "Presupuestos"
    subtitle = "Planeado vs comprometido vs devengado (control bloqueante)"
    columns = [
        ColumnSpec("Periodo", "date"),
        ColumnSpec("Cuenta", "date"),
        ColumnSpec("Nombre"),
        ColumnSpec("Planeado", "numeric"),
        ColumnSpec("Comprometido", "numeric"),
        ColumnSpec("Devengado", "numeric"),
        ColumnSpec("Disponible", "numeric"),
    ]

    def _load(self) -> None:
        self.set_table(self._presenter.budget_execution(date.today().year))

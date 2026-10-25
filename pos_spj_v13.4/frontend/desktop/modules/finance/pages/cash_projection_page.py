"""Proyección de flujo de efectivo (§32): planeación, separada de lo real.

Cobros por vencimiento de CxC, pagos programados o por vencer, gastos
aprobados, gastos recurrentes y la nómina estimada. Es una estimación: nunca
se mezcla con los estados financieros.
"""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.finance_view_models import KpiViewModel
from frontend.desktop.modules.finance.pages._page_base import FinancePage


class CashProjectionPage(FinancePage):
    title = "Proyección de flujo"
    subtitle = "Estimación semanal (planeación); no es un estado financiero"
    columns = [
        ColumnSpec("Semana", "date"),
        ColumnSpec("Entradas", "numeric"),
        ColumnSpec("Salidas", "numeric"),
        ColumnSpec("Neto", "numeric"),
        ColumnSpec("Saldo proyectado", "numeric"),
    ]

    def _load(self) -> None:
        data = self._presenter.cash_projection()
        self.set_kpis([KpiViewModel("Efectivo hoy", data["opening"]),
                       KpiViewModel("Nómina mensual estimada", data["payroll"], "warning")])
        self.set_table(data["table"])

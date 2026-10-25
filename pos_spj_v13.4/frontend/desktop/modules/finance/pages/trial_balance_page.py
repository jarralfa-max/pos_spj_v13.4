"""Balanza de comprobación (§31) en moneda base: siempre cuadra o falla."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.finance_view_models import KpiViewModel
from frontend.desktop.modules.finance.pages._page_base import FinancePage


class TrialBalancePage(FinancePage):
    title = "Balanza de comprobación"
    subtitle = "Débitos, créditos y saldo por cuenta de asientos contabilizados"
    period_filter = True
    columns = [
        ColumnSpec("Código", "date"),
        ColumnSpec("Cuenta"),
        ColumnSpec("Tipo", "status"),
        ColumnSpec("Debe", "numeric"),
        ColumnSpec("Haber", "numeric"),
        ColumnSpec("Saldo", "numeric"),
    ]

    def _load(self) -> None:
        data = self._presenter.trial_balance(*self.period())
        self.set_kpis([KpiViewModel("Total debe", data["debits"]),
                       KpiViewModel("Total haber", data["credits"])])
        self.set_table(data["table"])

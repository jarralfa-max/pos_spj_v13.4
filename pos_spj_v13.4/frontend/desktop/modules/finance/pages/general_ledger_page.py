"""Libro mayor y auxiliar por cuenta (§31): saldo inicial, movimientos con
saldo acumulado según la naturaleza de la cuenta y saldo final."""

from __future__ import annotations

from frontend.desktop.components.searchable_combo import SearchableComboBox
from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.finance_view_models import KpiViewModel, TableViewModel
from frontend.desktop.modules.finance.pages._page_base import FinancePage, compact_combo


class GeneralLedgerPage(FinancePage):
    title = "Libro mayor"
    subtitle = "Auxiliar de una cuenta en el periodo, en moneda base"
    period_filter = True
    empty_message = "Elija una cuenta para ver sus movimientos"
    columns = [
        ColumnSpec("Fecha", "date"),
        ColumnSpec("Asiento", "date"),
        ColumnSpec("Concepto"),
        ColumnSpec("Debe", "numeric"),
        ColumnSpec("Haber", "numeric"),
        ColumnSpec("Saldo", "numeric"),
    ]

    def _build_filters(self, row) -> None:
        self._account = SearchableComboBox(placeholder="Cuenta…")
        self._account.set_options(self._presenter.postable_accounts())
        self._account.selection_changed.connect(lambda *_: self._on_filter())
        compact_combo(self._account, 14)
        row.addWidget(self._account, stretch=1)

    def _load(self) -> None:
        account_id = self._account.current_id()
        if not account_id:
            self.set_table(TableViewModel([], []))
            return
        date_from, date_to = self.period()
        data = self._presenter.account_auxiliary(account_id, date_from, date_to)
        self.set_kpis([KpiViewModel("Saldo inicial", data["opening"]),
                       KpiViewModel("Saldo final", data["closing"], "success")])
        self.set_table(data["table"])

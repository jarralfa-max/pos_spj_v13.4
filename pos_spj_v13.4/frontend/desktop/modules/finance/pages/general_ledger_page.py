"""Libro mayor por cuenta."""

from __future__ import annotations

from PyQt5.QtWidgets import QComboBox

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage


class GeneralLedgerPage(FinancePage):
    title = "Libro mayor"
    subtitle = "Movimientos contabilizados por cuenta"
    columns = [
        ColumnSpec("Fecha", "date"),
        ColumnSpec("Asiento", "date"),
        ColumnSpec("Descripción"),
        ColumnSpec("Debe", "numeric"),
        ColumnSpec("Haber", "numeric"),
    ]

    def _build_actions(self) -> None:
        self._account_combo = QComboBox(self)
        self._account_combo.setMinimumWidth(320)
        self._account_combo.currentIndexChanged.connect(lambda _i: self._load_lines())
        self.header.add_action(self._account_combo)

    def _load(self) -> None:
        model = self._presenter.chart_of_accounts()
        self._account_combo.blockSignals(True)
        self._account_combo.clear()
        for row, account_id in zip(model.rows, model.row_ids):
            self._account_combo.addItem(f"{row[0]} — {row[1]}", account_id)
        self._account_combo.blockSignals(False)
        self._load_lines()

    def _load_lines(self) -> None:
        account_id = self._account_combo.currentData()
        if account_id:
            self.set_table(self._presenter.general_ledger(account_id))

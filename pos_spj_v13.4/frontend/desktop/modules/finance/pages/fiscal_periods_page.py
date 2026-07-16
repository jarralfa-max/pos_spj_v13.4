"""Periodos contables — cierre y reapertura controlada."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage
from modulos.ui_components import create_danger_button, create_secondary_button


class FiscalPeriodsPage(FinancePage):
    title = "Periodos contables"
    subtitle = "OPEN → SOFT_CLOSED → CLOSED; la reapertura exige motivo auditado"
    columns = [
        ColumnSpec("Periodo", "date"),
        ColumnSpec("Estado", "status"),
        ColumnSpec("Cerrado", "date"),
        ColumnSpec("Motivo de reapertura"),
    ]

    def _build_actions(self) -> None:
        close_btn = create_danger_button(self, "Cerrar periodo")
        close_btn.clicked.connect(self._close_period)
        reopen_btn = create_secondary_button(self, "Reabrir periodo")
        reopen_btn.clicked.connect(self._reopen_period)
        self.header.add_action(close_btn)
        self.header.add_action(reopen_btn)

    def _selected_period(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        code = self.table.item(row, 0).text()
        year, month = code.split("-")
        return int(year), int(month)

    def _close_period(self) -> None:
        period = self._selected_period()
        if not period:
            self.notify(False, "Seleccione un periodo.")
            return
        from frontend.desktop.modules.finance.dialogs.period_close_dialog import (
            PeriodCloseDialog,
        )
        dialog = PeriodCloseDialog(self)
        if dialog.exec_():
            self.notify(*self._presenter.close_period(*period, soft=dialog.is_soft()))

    def _reopen_period(self) -> None:
        period = self._selected_period()
        if not period:
            self.notify(False, "Seleccione un periodo.")
            return
        from frontend.desktop.modules.finance.dialogs.reversal_dialog import ReversalDialog
        dialog = ReversalDialog(self, title="Motivo de reapertura")
        if dialog.exec_():
            self.notify(*self._presenter.reopen_period(*period, dialog.reason()))

    def _load(self) -> None:
        self.set_table(self._presenter.fiscal_periods())

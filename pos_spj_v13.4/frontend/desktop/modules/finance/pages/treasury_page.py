"""Tesorería — posición y transferencias."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage
from modulos.ui_components import create_primary_button


class TreasuryPage(FinancePage):
    title = "Tesorería"
    subtitle = "Posición por cuenta (separada de la operación de Caja)"
    columns = [
        ColumnSpec("Cuenta"),
        ColumnSpec("Tipo", "status"),
        ColumnSpec("Saldo contable", "numeric"),
        ColumnSpec("Moneda", "status"),
    ]

    def _build_actions(self) -> None:
        transfer_btn = create_primary_button(self, "Transferir")
        transfer_btn.clicked.connect(self._transfer)
        self.header.add_action(transfer_btn)

    def _transfer(self) -> None:
        from frontend.desktop.modules.finance.dialogs.bank_transfer_dialog import (
            BankTransferDialog,
        )
        dialog = BankTransferDialog(self, self._presenter.treasury_accounts())
        if dialog.exec_():
            data = dialog.data()
            self.notify(*self._presenter.register_treasury_transfer(**data))

    def _load(self) -> None:
        self.set_table(self._presenter.treasury_position())

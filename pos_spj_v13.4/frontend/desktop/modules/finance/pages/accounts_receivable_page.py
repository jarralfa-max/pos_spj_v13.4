"""Cuentas por cobrar."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage
from modulos.ui_components import create_primary_button


class AccountsReceivablePage(FinancePage):
    title = "Cuentas por cobrar"
    subtitle = "Saldos abiertos con clientes"
    columns = [
        ColumnSpec("Documento", "date"),
        ColumnSpec("Cliente", "date"),
        ColumnSpec("Emisión", "date"),
        ColumnSpec("Vencimiento", "date"),
        ColumnSpec("Original", "numeric"),
        ColumnSpec("Saldo", "numeric"),
        ColumnSpec("Estado", "status"),
    ]

    def _build_actions(self) -> None:
        collect_btn = create_primary_button(self, "Registrar cobro")
        collect_btn.clicked.connect(self._collect)
        self.header.add_action(collect_btn)

    def _collect(self) -> None:
        receivable_id = self.table.selected_row_id()
        if not receivable_id:
            self.notify(False, "Seleccione una cuenta por cobrar.")
            return
        from frontend.desktop.modules.finance.dialogs.collection_dialog import CollectionDialog
        dialog = CollectionDialog(self, self._presenter.treasury_accounts())
        if dialog.exec_():
            data = dialog.data()
            self.notify(*self._presenter.register_collection(
                receivable_id=receivable_id, **data))

    def _load(self) -> None:
        self.set_table(self._presenter.open_receivables())

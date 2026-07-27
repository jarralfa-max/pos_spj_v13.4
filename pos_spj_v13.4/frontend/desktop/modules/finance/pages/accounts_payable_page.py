"""Cuentas por pagar."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage
from modulos.ui_components import create_primary_button


class AccountsPayablePage(FinancePage):
    title = "Cuentas por pagar"
    subtitle = "Obligaciones abiertas con proveedores (las compras nunca salen de Caja POS)"
    columns = [
        ColumnSpec("Documento", "date"),
        ColumnSpec("Proveedor", "date"),
        ColumnSpec("Emisión", "date"),
        ColumnSpec("Vencimiento", "date"),
        ColumnSpec("Original", "numeric"),
        ColumnSpec("Saldo", "numeric"),
        ColumnSpec("Estado", "status"),
    ]

    def _build_actions(self) -> None:
        schedule_btn = create_primary_button(self, "Programar pago")
        schedule_btn.clicked.connect(self._schedule)
        self.header.add_action(schedule_btn)

    def _schedule(self) -> None:
        payable_id = self.table.selected_row_id()
        if not payable_id:
            self.notify(False, "Seleccione una cuenta por pagar.")
            return
        from frontend.desktop.modules.finance.dialogs.supplier_payment_dialog import (
            SupplierPaymentDialog,
        )
        dialog = SupplierPaymentDialog(self, self._presenter.treasury_accounts())
        if dialog.exec_():
            data = dialog.data()
            self.notify(*self._presenter.schedule_supplier_payment(
                payable_id=payable_id, **data))

    def _load(self) -> None:
        self.set_table(self._presenter.open_payables())

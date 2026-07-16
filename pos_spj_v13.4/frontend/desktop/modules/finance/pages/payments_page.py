"""Pagos a proveedores — autorización y ejecución segregadas."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage
from modulos.ui_components import create_primary_button, create_success_button


class PaymentsPage(FinancePage):
    title = "Pagos a proveedores"
    subtitle = "Programar → Autorizar → Ejecutar → Conciliar (separación de funciones)"
    columns = [
        ColumnSpec("Referencia", "date"),
        ColumnSpec("Proveedor", "date"),
        ColumnSpec("Fecha programada", "date"),
        ColumnSpec("Importe", "numeric"),
        ColumnSpec("Estado", "status"),
        ColumnSpec("Autorizó", "date"),
    ]

    def _build_actions(self) -> None:
        authorize_btn = create_primary_button(self, "Autorizar")
        authorize_btn.clicked.connect(self._authorize)
        execute_btn = create_success_button(self, "Ejecutar")
        execute_btn.clicked.connect(self._execute)
        self.header.add_action(authorize_btn)
        self.header.add_action(execute_btn)

    def _authorize(self) -> None:
        payment_id = self.table.selected_row_id()
        if not payment_id:
            self.notify(False, "Seleccione un pago programado.")
            return
        self.notify(*self._presenter.authorize_supplier_payment(payment_id))

    def _execute(self) -> None:
        payment_id = self.table.selected_row_id()
        if not payment_id:
            self.notify(False, "Seleccione un pago autorizado.")
            return
        self.notify(*self._presenter.execute_supplier_payment(payment_id))

    def _load(self) -> None:
        self.set_table(self._presenter.supplier_payments())

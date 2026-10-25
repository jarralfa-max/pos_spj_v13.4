"""Cobros (§11): historial que permanece aunque la factura se liquide (F23) y
saldos a favor de clientes aplicables después a sus documentos."""

from __future__ import annotations

from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.finance.dialogs.collection_dialog import CollectionDialog
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P


class CollectionsPage(FinancePage):
    title = "Cobros"
    subtitle = "Historial de cobros y saldos a favor de clientes"
    searchable = True  # por referencia
    columns = [
        ColumnSpec("Fecha", "date"),
        ColumnSpec("Referencia", "date"),
        ColumnSpec("Cliente"),
        ColumnSpec("Cobrado", "numeric"),
        ColumnSpec("Aplicado", "numeric"),
        ColumnSpec("A favor", "numeric"),
        ColumnSpec("Cuenta"),
        ColumnSpec("Asiento", "date"),
        ColumnSpec("Estado", "status"),
    ]

    def _build_extra(self) -> None:
        self._credits = StandardTable([
            ColumnSpec("Fecha", "date"), ColumnSpec("Referencia", "date"),
            ColumnSpec("Cliente"), ColumnSpec("Cobrado", "numeric"),
            ColumnSpec("Disponible", "numeric"),
        ], self)
        self._credits.setMaximumHeight(170)
        self._layout.addWidget(self._credits)
        apply_button = create_secondary_button(self, "Aplicar saldo a favor")
        apply_button.clicked.connect(self._apply)
        self._guard(apply_button, P.COLLECTION_APPLY)
        self._layout.addWidget(apply_button)

    def _load(self) -> None:
        self.set_table(self._presenter.collection_history(search=self._search.query()))
        credits = self._presenter.customer_credit_balances()
        self._credits.load_rows(credits.rows, row_ids=credits.row_ids)

    def _apply(self) -> None:
        collection_id = self._credits.selected_row_id()
        credit = self._presenter.credit_balance(collection_id) if collection_id else None
        if credit is None:
            self.notify(False, "Elija el saldo a favor que desea aplicar.")
            return
        dialog = CollectionDialog(
            self, customer_label=credit["customer_name"],
            receivables=self._presenter.open_receivables_of(credit["customer_id"]),
            treasury_accounts=[], apply_only=True, available=credit["available"])
        if dialog.exec_():
            self.run(self._presenter.apply_collection(collection_id, dialog.applications()))

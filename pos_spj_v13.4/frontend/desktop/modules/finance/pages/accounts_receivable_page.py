"""Cuentas por cobrar."""

from __future__ import annotations

from PyQt5.QtWidgets import QInputDialog, QMessageBox

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage
from modulos.ui_components import create_primary_button, create_secondary_button


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

        # CRM-21: this page's table reads the newer `receivables` table
        # (via presenter.open_receivables()), which has no customer-search
        # UI at all today. This action reads `cuentas_por_cobrar` instead —
        # where real production CxC data actually lives — via
        # `presenter.crm_receivable_summary()`. Asks for the customer's
        # LEGACY id directly rather than a name/phone search: the CRM
        # customer-search index (`CustomerLookupQueryService`) only covers
        # the new Customer Master table, which today has no relationship to
        # `cuentas_por_cobrar.cliente_id` unless that specific customer has
        # already been bridged (migration 193) — a name search would find
        # the wrong population for most customers until the one-time
        # backfill (`tools/crm/backfill_legacy_customers.py`) has run.
        crm_btn = create_secondary_button(self, "Ver resumen CRM")
        crm_btn.clicked.connect(self._show_crm_summary)
        self.header.add_action(crm_btn)

    def _show_crm_summary(self) -> None:
        cliente_id, ok = QInputDialog.getText(
            self, "Resumen CRM", "ID de cliente (legacy):")
        if not ok or not cliente_id.strip():
            return
        self.show_crm_summary_for(cliente_id.strip())

    def show_crm_summary_for(self, cliente_id: str) -> None:
        """CRM-37 (Fase 3, NavigationIntent): entry point for arriving here
        already knowing WHICH customer — from Customer 360's "Ver CxC"
        action (`FinanceView.aplicar_contexto`) — instead of the cashier
        typing the legacy id by hand via `_show_crm_summary`'s
        `QInputDialog`. Same underlying call, same result dialog; the only
        difference is how `cliente_id` was obtained."""
        summary = self._presenter.crm_receivable_summary(cliente_id)
        if summary is None:
            self.notify(False, "No se encontró exposición CRM para ese cliente.")
            return
        QMessageBox.information(
            self, "Resumen CRM",
            f"Exposición actual: {summary['current_exposure']}\n"
            f"Vencido: {summary['overdue_amount']}\n"
            f"Próximo vencimiento: {summary['next_due_date'] or '—'}\n"
            f"Estatus: {summary['receivable_status']}")

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

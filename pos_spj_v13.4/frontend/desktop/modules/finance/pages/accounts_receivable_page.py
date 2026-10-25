"""Cuentas por cobrar (§11): documentos abiertos, cobro con aplicación
explícita, disputa, promesa de pago, castigo y vencimientos."""

from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.dialogs.collection_dialog import CollectionDialog
from frontend.desktop.modules.finance.dialogs.fields_dialog import (
    FieldSpec,
    ask,
    ask_entity,
    ask_reason,
)
from frontend.desktop.modules.finance.dialogs.table_dialog import TableDialog
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P


class AccountsReceivablePage(FinancePage):
    title = "Cuentas por cobrar"
    subtitle = "Saldos abiertos con clientes"
    searchable = True  # por folio
    _customer_filter: str | None = None
    columns = [
        ColumnSpec("Documento", "date"),
        ColumnSpec("Cliente"),
        ColumnSpec("Emisión", "date"),
        ColumnSpec("Vencimiento", "date"),
        ColumnSpec("Original", "numeric"),
        ColumnSpec("Saldo", "numeric"),
        ColumnSpec("Estado", "status"),
    ]
    header_actions = [
        ("Registrar cobro", P.COLLECTION_REGISTER, "_collect_for_customer", True),
        ("Nueva CxC", P.RECEIVABLE_MANAGE, "_create", False),
        ("Marcar vencidas", P.RECEIVABLE_MANAGE, "_mark_overdue", False),
    ]
    row_actions = [
        ("Cobrar", P.COLLECTION_REGISTER, "_collect_selected"),
        ("Disputa", P.CREDIT_MANAGE, "_dispute"),
        ("Resolver disputa", P.CREDIT_MANAGE, "_resolve"),
        ("Promesa de pago", P.CREDIT_MANAGE, "_promise"),
        ("Ver promesas", P.RECEIVABLE_READ, "_promises"),
        ("Castigar", P.WRITE_OFF_AUTHORIZE, "_write_off"),
    ]

    def _load(self) -> None:
        self.set_table(self._presenter.open_receivables(
            customer_id=self._customer_filter, search=self._search.query()))

    # ── enlace desde CRM (CRM-37) ────────────────────────────────────────
    def show_crm_summary_for(self, customer_id: str) -> None:
        """Llega desde Cliente 360 con el cliente ya resuelto: filtra la tabla
        por ese cliente y muestra su exposición de crédito."""
        self._customer_filter = customer_id
        self.reload()
        summary = self._presenter.crm_receivable_summary(customer_id)
        if summary is None:
            self.notify(False, "No se encontró exposición de crédito para ese cliente.")
            return
        QMessageBox.information(
            self, "Resumen de crédito",
            f"Exposición actual: {summary['current_exposure']}\n"
            f"Vencido: {summary['overdue_amount']}\n"
            f"Próximo vencimiento: {summary['next_due_date'] or '—'}\n"
            f"Estatus: {summary['receivable_status']}")

    # ── cobro ────────────────────────────────────────────────────────────
    def _collect(self, customer_id: str, customer_label: str,
                 preselected: str | None = None) -> None:
        p = self._presenter
        dialog = CollectionDialog(self, customer_label=customer_label,
                                  receivables=p.open_receivables_of(customer_id),
                                  treasury_accounts=p.treasury_accounts(money_only=True),
                                  preselected=preselected)
        if dialog.exec_():
            self.run(p.register_collection(customer_id=customer_id, **dialog.data()))

    def _collect_selected(self) -> None:
        found = self._presenter.receivable_customer(self.selected_id())
        if found:
            self._collect(found[0], found[1], preselected=self.selected_id())

    def _collect_for_customer(self) -> None:
        customer = ask_entity(self, "Registrar cobro", "Cliente",
                              self._presenter.customer_options)
        if customer:
            self._collect(*customer)

    # ── documento manual ─────────────────────────────────────────────────
    def _create(self) -> None:
        p = self._presenter
        values = ask(self, "Nueva cuenta por cobrar", [
            FieldSpec("customer_id", "Cliente", "search", required=True,
                      provider=p.customer_options),
            FieldSpec("document_number", "Folio del documento", required=True),
            FieldSpec("amount", "Importe", "money", required=True),
            FieldSpec("issue_date", "Fecha de emisión", "date", required=True,
                      default=p.today()),
            FieldSpec("credit_term_days", "Días de crédito", "int", maximum=365, default=0),
            FieldSpec("counterpart_account_id", "Cuenta de ingreso / contrapartida", "combo",
                      required=True, options=p.postable_accounts()),
        ])
        if values:
            values["credit_term_days"] = values["credit_term_days"] or None
            self.run(p.create_receivable(**values))

    def _mark_overdue(self) -> None:
        self.run(self._presenter.mark_overdue_documents())

    # ── seguimiento ──────────────────────────────────────────────────────
    def _dispute(self) -> None:
        reason = ask_reason(self, "Poner en disputa", "Motivo de la disputa")
        if reason:
            self.run(self._presenter.dispute_receivable(self.selected_id(), reason))

    def _resolve(self) -> None:
        resolution = ask_reason(self, "Resolver disputa", "Resolución")
        if resolution:
            self.run(self._presenter.resolve_receivable_dispute(self.selected_id(), resolution))

    def _promise(self) -> None:
        values = ask(self, "Promesa de pago", [
            FieldSpec("promised_date", "Fecha prometida", "date", required=True,
                      default=self._presenter.today()),
            FieldSpec("promised_amount", "Importe prometido", "money", required=True),
            FieldSpec("note", "Nota", "multiline"),
        ])
        if values:
            self.run(self._presenter.register_payment_promise(self.selected_id(), **values))

    def _promises(self) -> None:
        TableDialog(self, "Promesas de pago", [
            ColumnSpec("Fecha", "date"), ColumnSpec("Importe", "numeric"), ColumnSpec("Nota"),
            ColumnSpec("Estado", "status"),
        ], self._presenter.payment_promises(self.selected_id())).exec_()

    def _write_off(self) -> None:
        reason = ask_reason(self, "Castigar cuenta incobrable", "Motivo del castigo")
        if reason:
            self.run(self._presenter.write_off_receivable(self.selected_id(), reason))

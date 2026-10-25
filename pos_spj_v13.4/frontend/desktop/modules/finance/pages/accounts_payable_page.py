"""Cuentas por pagar (§12): documentos abiertos por prioridad, programación de
pago, bloqueo/desbloqueo, disputas y anticipos a proveedor."""

from __future__ import annotations

from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.finance.dialogs.fields_dialog import (
    FieldSpec,
    ask,
    ask_entity,
    ask_reason,
)
from frontend.desktop.modules.finance.pages._page_base import FinancePage, P


class AccountsPayablePage(FinancePage):
    title = "Cuentas por pagar"
    subtitle = "Documentos de proveedor abiertos, ordenados por prioridad y vencimiento"
    searchable = True  # por folio
    columns = [
        ColumnSpec("Documento", "date"),
        ColumnSpec("Proveedor"),
        ColumnSpec("Emisión", "date"),
        ColumnSpec("Vencimiento", "date"),
        ColumnSpec("Prioridad", "status"),
        ColumnSpec("Original", "numeric"),
        ColumnSpec("Saldo", "numeric"),
        ColumnSpec("Estado", "status"),
    ]
    header_actions = [
        ("Nueva CxP", P.PAYABLE_MANAGE, "_create", True),
        ("Anticipo a proveedor", P.PAYMENT_EXECUTE, "_advance", False),
    ]
    row_actions = [
        ("Programar pago", P.PAYMENT_SCHEDULE, "_schedule"),
        ("Aplicar anticipo", P.PAYABLE_MANAGE, "_apply_advance"),
        ("Bloquear", P.PAYABLE_MANAGE, "_block"),
        ("Desbloquear", P.PAYABLE_UNBLOCK, "_unblock"),
        ("Disputa", P.PAYABLE_MANAGE, "_dispute"),
        ("Resolver disputa", P.PAYABLE_MANAGE, "_resolve"),
    ]

    def _build_extra(self) -> None:
        self._advances = StandardTable([
            ColumnSpec("Fecha", "date"), ColumnSpec("Proveedor"), ColumnSpec("Referencia"),
            ColumnSpec("Importe", "numeric"), ColumnSpec("Disponible", "numeric"),
            ColumnSpec("Estado", "status"),
        ], self)
        self._advances.setMaximumHeight(150)
        self._layout.addWidget(self._advances)

    def _load(self) -> None:
        self.set_table(self._presenter.open_payables(search=self._search.query()))
        advances = self._presenter.supplier_advances()
        self._advances.load_rows(advances.rows, row_ids=advances.row_ids)

    def _create(self) -> None:
        p = self._presenter
        values = ask(self, "Nueva cuenta por pagar", [
            FieldSpec("supplier_id", "Proveedor", "search", required=True,
                      provider=p.supplier_options),
            FieldSpec("document_number", "Folio de la factura", required=True),
            FieldSpec("amount", "Importe total", "money", required=True),
            FieldSpec("issue_date", "Fecha de emisión", "date", required=True,
                      default=p.today()),
            FieldSpec("due_date", "Vencimiento", "date", default=p.today()),
            FieldSpec("debit_nature", "Naturaleza del cargo", "combo", required=True,
                      options=p.debit_nature_options(), default="OPERATING_EXPENSE"),
            FieldSpec("counterpart_account_id", "Cuenta de cargo (gasto/activo)", "combo",
                      options=p.postable_accounts()),
            FieldSpec("retention_amount", "Retenciones", "money", allow_zero=True),
            FieldSpec("priority", "Prioridad", "combo", required=True,
                      options=p.priority_options(), default="NORMAL"),
            FieldSpec("payment_terms", "Condiciones de pago"),
        ])
        if values:
            if values["retention_amount"] in ("0", "0.00"):
                values["retention_amount"] = None
            self.run(p.create_payable(**values))

    def _schedule(self) -> None:
        payable = self._presenter.payable_summary(self.selected_id())
        if payable is None:
            return
        p = self._presenter
        values = ask(self, f"Programar pago de {payable['document_number']}", [
            FieldSpec("info", "", "info",
                      default=f"Saldo {payable['outstanding_amount']} {payable['currency_code']}."
                              " Programar no mueve dinero: falta autorizar y ejecutar."),
            FieldSpec("amount", "Importe", "money", required=True,
                      default=payable["outstanding_amount"]),
            FieldSpec("treasury_account_id", "Cuenta de pago", "combo", required=True,
                      options=p.treasury_accounts(money_only=True)),
            FieldSpec("scheduled_date", "Fecha programada", "date", required=True,
                      default=p.today()),
            FieldSpec("reference", "Referencia"),
        ])
        if values:
            self.run(p.schedule_supplier_payment(payable_id=payable["id"], **values))

    def _advance(self) -> None:
        p = self._presenter
        supplier = ask_entity(self, "Anticipo a proveedor", "Proveedor", p.supplier_options)
        if not supplier:
            return
        values = ask(self, f"Anticipo a {supplier[1]}", [
            FieldSpec("amount", "Importe", "money", required=True),
            FieldSpec("treasury_account_id", "Cuenta de pago", "combo", required=True,
                      options=p.treasury_accounts(money_only=True)),
            FieldSpec("execution_reference", "Evidencia del pago (SPEI, cheque)", required=True),
        ])
        if values:
            self.run(p.register_supplier_advance(supplier_id=supplier[0], **values))

    def _apply_advance(self) -> None:
        payable = self._presenter.payable_summary(self.selected_id())
        if payable is None:
            return
        advances = self._presenter.advances_of(payable["supplier_id"])
        if not advances:
            self.notify(False, "El proveedor no tiene anticipos disponibles.")
            return
        values = ask(self, f"Aplicar anticipo a {payable['document_number']}", [
            FieldSpec("supplier_advance_id", "Anticipo", "combo", required=True,
                      options=advances),
            FieldSpec("amount", "Importe a aplicar", "money", required=True,
                      default=payable["outstanding_amount"]),
        ])
        if values:
            self.run(self._presenter.apply_supplier_advance(payable_id=payable["id"], **values))

    def _block(self) -> None:
        reason = ask_reason(self, "Bloquear CxP", "Motivo del bloqueo")
        if reason:
            self.run(self._presenter.block_payable(self.selected_id(), reason))

    def _unblock(self) -> None:
        reason = ask_reason(self, "Desbloquear CxP", "Motivo del desbloqueo")
        if reason:
            self.run(self._presenter.unblock_payable(self.selected_id(), reason))

    def _dispute(self) -> None:
        reason = ask_reason(self, "Poner en disputa", "Motivo de la disputa")
        if reason:
            self.run(self._presenter.dispute_payable(self.selected_id(), reason))

    def _resolve(self) -> None:
        resolution = ask_reason(self, "Resolver disputa", "Resolución")
        if resolution:
            self.run(self._presenter.resolve_payable_dispute(self.selected_id(), resolution))

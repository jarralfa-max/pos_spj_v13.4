"""PURCHASE_RECEIVED / SUPPLIER_INVOICE_REGISTERED handlers.

Purchases NEVER touch the POS cash register. A received purchase recognizes
inventory against accounts payable; payment happens later through the
segregated supplier-payment route (schedule → authorize → execute).
"""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.entities.financial_document import FinancialDocument
from backend.domain.finance.entities.payable import Payable
from backend.domain.finance.enums import (
    FinancialDocumentType,
    JournalType,
    PostingPurpose,
)
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.posting_reference import PostingReference
from backend.shared.ids import new_uuid


class PurchaseReceivedHandler(FinanceEventHandler):
    event_name = "PURCHASE_RECEIVED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        currency = self.currency(payload)
        purchase_id = str(payload.get("purchase_id") or "")
        supplier_id = str(payload.get("supplier_id") or "")
        if not purchase_id or not supplier_id:
            raise FinanceDomainError("PURCHASE_RECEIVED requiere purchase_id y supplier_id")
        entry_date = self.event_date(payload)
        branch_id = payload.get("branch_id")
        folio = str(payload.get("folio") or purchase_id[:8])

        subtotal = self.money(payload, "subtotal", currency)
        tax = self.money(payload, "tax_total", currency, required=False)
        total = self.money(payload, "total", currency)
        if subtotal.add(tax).amount != total.amount:
            raise FinanceDomainError(
                f"Compra {folio}: subtotal + impuestos != total"
            )

        profile = self.resolve_profile(uow, "PURCHASE", entry_date)
        lines = [
            LineSpec(profile.account_for("inventory_account_id"), debit=subtotal,
                     description=f"Recepción de inventario compra {folio}"),
        ]
        if tax.is_positive():
            lines.append(LineSpec(profile.account_for("tax_account_id"), debit=tax,
                                  description=f"IVA acreditable compra {folio}"))
        lines.append(LineSpec(profile.account_for("payable_account_id"), credit=total,
                              description=f"CxP proveedor compra {folio}"))

        self._engine.post(
            uow, JournalType.PURCHASES, entry_date, f"Compra recibida {folio}",
            PostingReference("purchases", purchase_id, PostingPurpose.PURCHASE_RECEIPT,
                             str(payload["operation_id"])),
            lines, currency_code=currency, branch_id=branch_id,
        )

        existing_docs = uow.financial_documents.find_by_source("purchases", purchase_id)
        if not any(d.document_type is FinancialDocumentType.SUPPLIER_INVOICE for d in existing_docs):
            document = FinancialDocument.create(
                FinancialDocumentType.SUPPLIER_INVOICE, folio, entry_date, total,
                "purchases", purchase_id, new_uuid(),
                branch_id=branch_id, supplier_id=supplier_id,
            )
            uow.financial_documents.save(document)
            payable = Payable.create(
                supplier_id, document.id, total, entry_date, new_uuid(),
                branch_id=branch_id,
            )
            uow.payables.save(payable)

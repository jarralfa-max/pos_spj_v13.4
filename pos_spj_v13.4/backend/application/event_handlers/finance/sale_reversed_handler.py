"""SALE_REVERSED / SALE_CANCELLED handler — reversal entries, never edits."""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.enums import JournalEntryStatus, PostingPurpose, ReceivableStatus
from backend.domain.finance.exceptions import FinanceDomainError
from backend.shared.ids import new_uuid


class SaleReversedHandler(FinanceEventHandler):
    event_name = "SALE_REVERSED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        sale_id = str(payload.get("sale_id") or "")
        if not sale_id:
            raise FinanceDomainError("SALE_REVERSED sin sale_id")
        reason = str(payload.get("reason") or "Venta cancelada/devuelta")
        reversal_date = self.event_date(payload)

        reversed_any = False
        for purpose in (PostingPurpose.SALE_REVENUE, PostingPurpose.SALE_COGS):
            original = uow.journal_entries.find_by_posting_reference("sales", sale_id, purpose)
            if original is None:
                continue
            if original.status is JournalEntryStatus.REVERSED:
                reversed_any = True
                continue
            self._engine.reverse(uow, original, reversal_date, reason, new_uuid())
            reversed_any = True
        if not reversed_any:
            raise FinanceDomainError(
                f"SALE_REVERSED: no existe asiento contabilizado para la venta {sale_id}"
            )

        # Cancel the open receivable of a reversed credit sale.
        for document in uow.financial_documents.find_by_source("sales", sale_id):
            receivable = uow.receivables.find_by_document(document.id)
            if receivable is not None and receivable.status in (
                ReceivableStatus.OPEN, ReceivableStatus.PARTIALLY_COLLECTED,
            ):
                receivable.cancel()
                uow.receivables.update(receivable)
                document.cancel()
                uow.financial_documents.update(document)

"""LOYALTY_TRANSACTION_REVERSED — mirror reversal; originals are never edited."""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.commercial_instrument_processor import (
    CommercialInstrumentProcessor,
)
from backend.domain.finance.enums import CommercialInstrumentType
from backend.domain.finance.exceptions import FinanceDomainError


class LoyaltyTransactionReversedHandler(FinanceEventHandler):
    event_name = "LOYALTY_TRANSACTION_REVERSED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._processor = CommercialInstrumentProcessor()

    def _handle(self, uow, payload: dict) -> None:
        transaction_id = str(payload.get("loyalty_transaction_id") or "")
        if not transaction_id:
            raise FinanceDomainError("LOYALTY_TRANSACTION_REVERSED sin loyalty_transaction_id")
        self._processor.reverse(
            uow,
            instrument_type=CommercialInstrumentType.LOYALTY_POINTS,
            source_instrument_id=transaction_id,
            on_date=self.event_date(payload),
            operation_id=str(payload["operation_id"]),
            reason=str(payload.get("reason") or "Reverso de transacción de fidelidad"),
        )

"""LOYALTY_POINTS_EXPIRED — releases the obligation into breakage income.

Expiration never silently deletes the obligation: the release is posted and
fully traceable.
"""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.commercial_instrument_processor import (
    CommercialInstrumentProcessor,
)
from backend.domain.finance.enums import CommercialInstrumentType
from backend.domain.finance.exceptions import FinanceDomainError


class LoyaltyPointsExpiredHandler(FinanceEventHandler):
    event_name = "LOYALTY_POINTS_EXPIRED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._processor = CommercialInstrumentProcessor()

    def _handle(self, uow, payload: dict) -> None:
        transaction_id = str(payload.get("loyalty_transaction_id") or "")
        if not transaction_id:
            raise FinanceDomainError("LOYALTY_POINTS_EXPIRED sin loyalty_transaction_id")
        currency = self.currency(payload)
        amount = None
        if payload.get("expired_value") not in (None, ""):
            amount = self.money(payload, "expired_value", currency)
        self._processor.expire(
            uow,
            instrument_type=CommercialInstrumentType.LOYALTY_POINTS,
            source_instrument_id=transaction_id,
            on_date=self.event_date(payload),
            operation_id=str(payload["operation_id"]),
            amount=amount,
        )

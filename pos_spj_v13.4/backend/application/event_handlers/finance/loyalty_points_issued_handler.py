"""LOYALTY_POINTS_ISSUED — recognizes the estimated points obligation.

Loyalty owns programs, rules and points. Finance only recognizes the economic
effect using the configured posting profile (contra-revenue or expense against
the pending-points liability). Points are never a monetary unit by themselves:
the event carries ``estimated_fair_value`` as a decimal string.
"""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.commercial_instrument_processor import (
    CommercialInstrumentProcessor,
)
from backend.domain.finance.enums import CommercialInstrumentType
from backend.domain.finance.exceptions import FinanceDomainError


class LoyaltyPointsIssuedHandler(FinanceEventHandler):
    event_name = "LOYALTY_POINTS_ISSUED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._processor = CommercialInstrumentProcessor()

    def _handle(self, uow, payload: dict) -> None:
        transaction_id = str(payload.get("loyalty_transaction_id") or "")
        if not transaction_id:
            raise FinanceDomainError("LOYALTY_POINTS_ISSUED sin loyalty_transaction_id")
        currency = self.currency(payload)
        value = self.money(payload, "estimated_fair_value", currency)
        self._processor.recognize(
            uow,
            instrument_type=CommercialInstrumentType.LOYALTY_POINTS,
            source_module="loyalty",
            source_instrument_id=transaction_id,
            amount=value,
            on_date=self.event_date(payload),
            operation_id=str(payload["operation_id"]),
            customer_id=payload.get("customer_id"),
            branch_id=payload.get("branch_id"),
            program_id=payload.get("program_id"),
            campaign_id=payload.get("campaign_id"),
            expires_at=payload.get("expires_at"),
        )

"""LOYALTY_POINTS_REDEEMED — cancels the obligation; recognizes cost deltas.

The event may carry ``actual_reward_cost``: the difference between estimated
fair value and actual cost posts as expense or breakage income.
"""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.commercial_instrument_processor import (
    CommercialInstrumentProcessor,
)
from backend.domain.finance.enums import CommercialInstrumentType
from backend.domain.finance.exceptions import FinanceDomainError


class LoyaltyPointsRedeemedHandler(FinanceEventHandler):
    event_name = "LOYALTY_POINTS_REDEEMED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._processor = CommercialInstrumentProcessor()

    def _handle(self, uow, payload: dict) -> None:
        transaction_id = str(payload.get("loyalty_transaction_id") or "")
        if not transaction_id:
            raise FinanceDomainError("LOYALTY_POINTS_REDEEMED sin loyalty_transaction_id")
        currency = self.currency(payload)
        redeemed_value = self.money(payload, "redeemed_value", currency)
        actual_cost = None
        if payload.get("actual_reward_cost") not in (None, ""):
            actual_cost = self.money(payload, "actual_reward_cost", currency)
        self._processor.redeem(
            uow,
            instrument_type=CommercialInstrumentType.LOYALTY_POINTS,
            source_instrument_id=transaction_id,
            amount=redeemed_value,
            on_date=self.event_date(payload),
            operation_id=str(payload["operation_id"]),
            redemption_id=payload.get("loyalty_redemption_id"),
            actual_cost=actual_cost,
        )

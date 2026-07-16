"""LOYALTY_REWARD_GRANTED — a reward delivered without redeeming points.

Recognized as promotional/loyalty expense; when it delivers inventory the
event carries ``reward_cost`` and inventory leaves at cost.
"""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.enums import CommercialInstrumentType, JournalType, PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.posting_reference import PostingReference


class LoyaltyRewardGrantedHandler(FinanceEventHandler):
    event_name = "LOYALTY_REWARD_GRANTED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        reward_id = str(payload.get("reward_id") or payload.get("loyalty_transaction_id") or "")
        if not reward_id:
            raise FinanceDomainError("LOYALTY_REWARD_GRANTED sin reward_id")
        currency = self.currency(payload)
        cost = self.money(payload, "reward_cost", currency)
        entry_date = self.event_date(payload)
        profile = self.resolve_profile(
            uow, CommercialInstrumentType.LOYALTY_POINTS.value, entry_date,
            instrument_type=CommercialInstrumentType.LOYALTY_POINTS,
        )
        delivers_inventory = bool(payload.get("delivers_inventory"))
        credit_role = "inventory_account_id" if delivers_inventory else "clearing_account_id"
        self._engine.post(
            uow, JournalType.LOYALTY, entry_date,
            f"Recompensa de fidelidad {reward_id[:8]}",
            PostingReference("loyalty", reward_id, PostingPurpose.INSTRUMENT_RECOGNITION,
                             str(payload["operation_id"])),
            [
                LineSpec(profile.account_for("expense_account_id"), debit=cost,
                         description="Gasto por recompensa de fidelidad"),
                LineSpec(profile.account_for(credit_role), credit=cost,
                         description="Entrega de recompensa"),
            ],
            currency_code=currency, branch_id=payload.get("branch_id"),
        )

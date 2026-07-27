"""WASTE_REGISTERED handler — waste is a cost, never a cash movement."""

from __future__ import annotations

from backend.application.event_handlers.finance.handler_base import FinanceEventHandler
from backend.application.services.finance.posting_engine import PostingEngine
from backend.domain.finance.enums import JournalType, PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.services.journal_posting_service import LineSpec
from backend.domain.finance.value_objects.posting_reference import PostingReference


class WasteRegisteredHandler(FinanceEventHandler):
    """WASTE_REGISTERED — waste is a cost, never a cash movement."""

    event_name = "WASTE_REGISTERED"

    def __init__(self, connection) -> None:
        super().__init__(connection)
        self._engine = PostingEngine()

    def _handle(self, uow, payload: dict) -> None:
        currency = self.currency(payload)
        waste_id = str(payload.get("waste_id") or "")
        if not waste_id:
            raise FinanceDomainError("WASTE_REGISTERED sin waste_id")
        entry_date = self.event_date(payload)
        amount = self.money(payload, "amount", currency)
        profile = self.resolve_profile(uow, "INVENTORY", entry_date)
        self._engine.post(
            uow, JournalType.INVENTORY, entry_date, f"Merma {waste_id[:8]}",
            PostingReference("inventory", waste_id, PostingPurpose.WASTE,
                             str(payload["operation_id"])),
            [
                LineSpec(profile.account_for("waste_expense_account_id"), debit=amount,
                         description="Costo de merma"),
                LineSpec(profile.account_for("inventory_account_id"), credit=amount,
                         description="Salida de inventario por merma"),
            ],
            currency_code=currency, branch_id=payload.get("branch_id"),
        )

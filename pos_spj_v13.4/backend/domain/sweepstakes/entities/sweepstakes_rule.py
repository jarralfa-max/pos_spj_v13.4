"""SweepstakesRule — one-per-campaign entry-earning configuration (master
prompt §27). Mirrors the legacy `raffle_rules` table's own shape
(ticket_strategy/amount_per_ticket/max_tickets_per_customer), rebuilt with
Decimal money and a real entry-method enum instead of a free-text
`ticket_strategy` string."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.sweepstakes.enums import SweepstakesEntryMethod
from backend.domain.sweepstakes.exceptions import InvalidSweepstakesRuleError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class SweepstakesRule:
    id: str
    campaign_id: str
    entry_method: SweepstakesEntryMethod
    amount_per_ticket: Decimal = Decimal("0")
    tickets_per_sale: int = 1
    max_tickets_per_sale: int = 0
    max_tickets_per_customer: int = 0
    requires_registered_customer: bool = True
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.campaign_id:
            raise InvalidSweepstakesRuleError("campaign_id es obligatorio")
        if isinstance(self.amount_per_ticket, (bool, float)):
            raise InvalidSweepstakesRuleError("amount_per_ticket debe ser Decimal, nunca float")
        self.amount_per_ticket = Decimal(str(self.amount_per_ticket))
        if self.entry_method is SweepstakesEntryMethod.PURCHASE_AMOUNT and self.amount_per_ticket <= 0:
            raise InvalidSweepstakesRuleError(
                "amount_per_ticket debe ser positivo para PURCHASE_AMOUNT")
        if self.tickets_per_sale <= 0:
            raise InvalidSweepstakesRuleError("tickets_per_sale debe ser positivo")
        if self.max_tickets_per_sale < 0 or self.max_tickets_per_customer < 0:
            raise InvalidSweepstakesRuleError("los máximos no pueden ser negativos")

    @classmethod
    def create(cls, campaign_id: str, entry_method: SweepstakesEntryMethod, **kwargs) -> "SweepstakesRule":
        return cls(id=new_uuid(), campaign_id=campaign_id, entry_method=entry_method, **kwargs)

    def chances_for_amount(self, sale_amount: Decimal) -> int:
        """§27: how many chances a sale of `sale_amount` earns under this
        rule. Only meaningful for PURCHASE_AMOUNT; other entry methods grant
        a flat `tickets_per_sale` regardless of amount."""
        if self.entry_method is not SweepstakesEntryMethod.PURCHASE_AMOUNT:
            chances = self.tickets_per_sale
        else:
            if isinstance(sale_amount, (bool, float)):
                raise InvalidSweepstakesRuleError("sale_amount debe ser Decimal, nunca float")
            sale_amount = Decimal(str(sale_amount))
            chances = int(sale_amount // self.amount_per_ticket) if sale_amount > 0 else 0
        if self.max_tickets_per_sale > 0:
            chances = min(chances, self.max_tickets_per_sale)
        return max(chances, 0)

"""SweepstakesEntry — an immutable record of earned chances (master prompt
§27-28). This is the "derecho previo" §28 requires to exist BEFORE any
SweepstakesTicket can be issued — an entry is never edited or deleted once
created, only ever added (same append-only discipline as
`backend.domain.loyalty.entities.loyalty_transaction.LoyaltyTransaction`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.sweepstakes.enums import SweepstakesEntryMethod
from backend.domain.sweepstakes.exceptions import InvalidSweepstakesEntryError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class SweepstakesEntry:
    id: str
    campaign_id: str
    customer_id: str
    entry_method: SweepstakesEntryMethod
    chances_granted: int = 1
    source_sale_id: str | None = None
    notes: str = ""
    granted_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.campaign_id:
            raise InvalidSweepstakesEntryError("campaign_id es obligatorio")
        if not self.customer_id:
            raise InvalidSweepstakesEntryError("customer_id es obligatorio")
        if self.chances_granted <= 0:
            raise InvalidSweepstakesEntryError("chances_granted debe ser positivo")
        if self.entry_method is SweepstakesEntryMethod.PURCHASE_AMOUNT and not self.source_sale_id:
            raise InvalidSweepstakesEntryError("PURCHASE_AMOUNT requiere source_sale_id")

    @classmethod
    def grant(cls, campaign_id: str, customer_id: str, entry_method: SweepstakesEntryMethod,
              **kwargs) -> "SweepstakesEntry":
        return cls(id=new_uuid(), campaign_id=campaign_id, customer_id=customer_id,
                    entry_method=entry_method, **kwargs)

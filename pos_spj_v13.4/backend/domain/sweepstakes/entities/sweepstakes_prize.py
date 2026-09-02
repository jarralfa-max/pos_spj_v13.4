"""SweepstakesPrize — one prize offered by a campaign, drawn in `rank`
order (master prompt §27)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.sweepstakes.enums import SweepstakesPrizeStatus
from backend.domain.sweepstakes.exceptions import InvalidSweepstakesPrizeError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class SweepstakesPrize:
    id: str
    campaign_id: str
    name: str
    description: str = ""
    quantity: int = 1
    rank: int = 1
    estimated_cost: Decimal = Decimal("0")
    status: SweepstakesPrizeStatus = SweepstakesPrizeStatus.PENDING
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.campaign_id:
            raise InvalidSweepstakesPrizeError("campaign_id es obligatorio")
        if not self.name or not self.name.strip():
            raise InvalidSweepstakesPrizeError("name es obligatorio")
        if self.quantity <= 0:
            raise InvalidSweepstakesPrizeError("quantity debe ser positivo")
        if self.rank <= 0:
            raise InvalidSweepstakesPrizeError("rank debe ser positivo")
        if isinstance(self.estimated_cost, (bool, float)):
            raise InvalidSweepstakesPrizeError("estimated_cost debe ser Decimal, nunca float")
        self.estimated_cost = Decimal(str(self.estimated_cost))
        if self.estimated_cost < 0:
            raise InvalidSweepstakesPrizeError("estimated_cost no puede ser negativo")

    @classmethod
    def create(cls, campaign_id: str, name: str, **kwargs) -> "SweepstakesPrize":
        return cls(id=new_uuid(), campaign_id=campaign_id, name=name.strip(), **kwargs)

    def mark_assigned(self) -> None:
        self.status = SweepstakesPrizeStatus.ASSIGNED

    def mark_delivered(self) -> None:
        self.status = SweepstakesPrizeStatus.DELIVERED

"""LoyaltyTierHistory — an immutable record of a tier change (master prompt
§14: "Toda modificación de nivel debe dejar historial"). Append-only, no
transition methods — created once, never mutated."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty.exceptions import InvalidLoyaltyTierError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class LoyaltyTierHistory:
    id: str
    membership_id: str
    previous_tier_id: str | None
    new_tier_id: str | None
    reason: str
    evaluated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.membership_id:
            raise InvalidLoyaltyTierError("membership_id es obligatorio")
        if self.previous_tier_id == self.new_tier_id:
            raise InvalidLoyaltyTierError(
                "Un historial de nivel requiere un cambio real (previous != new)")

    @classmethod
    def record(cls, membership_id: str, *, previous_tier_id: str | None,
               new_tier_id: str | None, reason: str) -> "LoyaltyTierHistory":
        return cls(id=new_uuid(), membership_id=membership_id,
                   previous_tier_id=previous_tier_id, new_tier_id=new_tier_id,
                   reason=reason)

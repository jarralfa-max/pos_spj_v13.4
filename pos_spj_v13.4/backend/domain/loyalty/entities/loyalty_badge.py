"""LoyaltyBadge — an immutable award record (master prompt §16). Append-only,
mirrors `LoyaltyTierHistory`'s frozen shape."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty.exceptions import InvalidChallengeProgressError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class LoyaltyBadge:
    id: str
    membership_id: str
    badge_code: str
    source_challenge_id: str | None = None
    earned_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.membership_id:
            raise InvalidChallengeProgressError("LoyaltyBadge requiere membership_id")
        if not self.badge_code or not self.badge_code.strip():
            raise InvalidChallengeProgressError("badge_code es obligatorio")

    @classmethod
    def award(cls, membership_id: str, badge_code: str, *,
              source_challenge_id: str | None = None) -> "LoyaltyBadge":
        return cls(id=new_uuid(), membership_id=membership_id, badge_code=badge_code.strip(),
                   source_challenge_id=source_challenge_id)

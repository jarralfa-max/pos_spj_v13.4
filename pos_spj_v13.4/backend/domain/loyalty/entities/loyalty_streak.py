"""LoyaltyStreak — consecutive-activity tracking (master prompt §16:
``CONSECUTIVE_WEEKS``, "Rachas"). ``period`` is an opaque, caller-supplied
string identifying a discrete period (e.g. an ISO week ``"2026-W35"``) —
this entity has no calendar logic of its own, it only compares the new
period against the last recorded one for equality/adjacency, which the
caller determines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty.exceptions import InvalidChallengeProgressError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class LoyaltyStreak:
    id: str
    membership_id: str
    streak_type: str
    current_count: int = 0
    longest_count: int = 0
    last_period: str | None = None
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def start(cls, membership_id: str, streak_type: str) -> "LoyaltyStreak":
        if not membership_id:
            raise InvalidChallengeProgressError("LoyaltyStreak requiere membership_id")
        if not streak_type or not streak_type.strip():
            raise InvalidChallengeProgressError("streak_type es obligatorio")
        return cls(id=new_uuid(), membership_id=membership_id, streak_type=streak_type.strip())

    def record_period(self, period: str, *, is_consecutive: bool) -> None:
        """``is_consecutive`` is decided by the caller (it knows the
        calendar semantics of ``streak_type`` — weekly/monthly/etc.) — this
        entity only tracks the resulting counters, same "no calendar logic
        in the entity" boundary as `LoyaltyProgram.effective_from` fields
        elsewhere in this bounded context.

        Recording the SAME period twice is a no-op (idempotent) rather than
        double-incrementing the streak."""
        if period == self.last_period:
            return
        if is_consecutive:
            self.current_count += 1
        else:
            self.current_count = 1
        self.longest_count = max(self.longest_count, self.current_count)
        self.last_period = period
        self.updated_at = _utcnow()

    def reset(self) -> None:
        self.current_count = 0
        self.last_period = None
        self.updated_at = _utcnow()

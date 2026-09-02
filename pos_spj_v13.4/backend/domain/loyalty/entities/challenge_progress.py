"""ChallengeProgress — one membership's progress toward one LoyaltyChallenge
(master prompt §16). Field shape mirrors the legacy
`loyalty_challenge_progress` table's own real, sensible shape
(`current_value`/`completed`/`completed_at`/`points_awarded` —
`migrations/m000_base_schema.py::_create_loyalty`) — preserving valid prior
design (CLAUDE.md Prioridad 0) even though the table itself is superseded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.loyalty.exceptions import InvalidChallengeProgressError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class ChallengeProgress:
    id: str
    challenge_id: str
    membership_id: str
    current_value: Decimal = Decimal("0")
    completed: bool = False
    completed_at: str | None = None
    points_awarded: Decimal = Decimal("0")
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def start(cls, challenge_id: str, membership_id: str) -> "ChallengeProgress":
        if not challenge_id or not membership_id:
            raise InvalidChallengeProgressError(
                "ChallengeProgress requiere challenge_id y membership_id")
        return cls(id=new_uuid(), challenge_id=challenge_id, membership_id=membership_id)

    def increment(self, amount: Decimal) -> None:
        if self.completed:
            raise InvalidChallengeProgressError(
                "No se puede avanzar un progreso ya completado")
        if isinstance(amount, bool) or isinstance(amount, float):
            raise InvalidChallengeProgressError("amount debe ser Decimal, nunca float")
        amount = Decimal(str(amount))
        if amount <= 0:
            raise InvalidChallengeProgressError("El incremento debe ser positivo")
        self.current_value += amount
        self.updated_at = _utcnow()

    def mark_completed(self, points_awarded: Decimal) -> None:
        if self.completed:
            raise InvalidChallengeProgressError("El progreso ya estaba completado")
        self.completed = True
        self.completed_at = _utcnow()
        self.points_awarded = Decimal(str(points_awarded))
        self.updated_at = self.completed_at

    def has_reached(self, target_value: Decimal) -> bool:
        return self.current_value >= target_value

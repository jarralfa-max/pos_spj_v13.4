"""LoyaltyMembership — a LoyaltyAccount's enrollment in one LoyaltyProgram
(§10). A single account may hold several memberships (multi-program, §9).

``current_tier_id`` is a plain reference; LOY-7 (Niveles) owns tier
evaluation/history — this entity only records the current pointer and lets
``change_tier`` update it (tier-change events belong to whoever calls it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty.enums import MembershipStatus
from backend.domain.loyalty.exceptions import InvalidLoyaltyMembershipStateError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class LoyaltyMembership:
    id: str
    loyalty_account_id: str
    program_id: str
    current_tier_id: str | None = None
    status: MembershipStatus = MembershipStatus.ACTIVE
    enrolled_at: str = field(default_factory=_utcnow)
    suspended_at: str | None = None
    closed_at: str | None = None
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def enroll(cls, loyalty_account_id: str, program_id: str) -> "LoyaltyMembership":
        if not loyalty_account_id:
            raise InvalidLoyaltyMembershipStateError("Se requiere loyalty_account_id")
        if not program_id:
            raise InvalidLoyaltyMembershipStateError("Se requiere program_id")
        return cls(id=new_uuid(), loyalty_account_id=loyalty_account_id, program_id=program_id)

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def suspend(self, reason: str) -> None:
        if self.status is not MembershipStatus.ACTIVE:
            raise InvalidLoyaltyMembershipStateError(
                f"Solo se suspende una membresía activa (actual: {self.status.value})")
        if not (reason or "").strip():
            raise InvalidLoyaltyMembershipStateError("La suspensión requiere un motivo")
        self.status = MembershipStatus.SUSPENDED
        self.suspended_at = _utcnow()
        self._touch()

    def block(self, reason: str) -> None:
        if self.status in (MembershipStatus.CLOSED, MembershipStatus.BLOCKED):
            raise InvalidLoyaltyMembershipStateError(
                f"No se puede bloquear desde {self.status.value}")
        if not (reason or "").strip():
            raise InvalidLoyaltyMembershipStateError("El bloqueo requiere un motivo")
        self.status = MembershipStatus.BLOCKED
        self._touch()

    def reactivate(self) -> None:
        if self.status not in (MembershipStatus.SUSPENDED, MembershipStatus.BLOCKED):
            raise InvalidLoyaltyMembershipStateError(
                f"No se puede reactivar desde {self.status.value}")
        self.status = MembershipStatus.ACTIVE
        self.suspended_at = None
        self._touch()

    def close(self, reason: str) -> None:
        if self.status is MembershipStatus.CLOSED:
            raise InvalidLoyaltyMembershipStateError("La membresía ya está cerrada")
        if not (reason or "").strip():
            raise InvalidLoyaltyMembershipStateError("El cierre requiere un motivo")
        self.status = MembershipStatus.CLOSED
        self.closed_at = _utcnow()
        self._touch()

    def change_tier(self, tier_id: str | None) -> None:
        self.current_tier_id = tier_id
        self._touch()

    def is_operational(self) -> bool:
        return self.status is MembershipStatus.ACTIVE

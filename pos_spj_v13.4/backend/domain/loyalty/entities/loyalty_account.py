"""LoyaltyAccount — the customer's single Fidelidad account (§10).

Sits between Customer and LoyaltyMembership: ``Customer → LoyaltyAccount →
LoyaltyMembership``. Never duplicates customer identity data (name, phone,
email — master prompt §4/§52) — only ``customer_id`` as a cross-context
reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty.enums import AccountStatus
from backend.domain.loyalty.exceptions import InvalidLoyaltyAccountStateError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class LoyaltyAccount:
    id: str
    customer_id: str
    status: AccountStatus = AccountStatus.ACTIVE
    suspended_at: str | None = None
    closed_at: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, customer_id: str) -> "LoyaltyAccount":
        if not customer_id:
            raise InvalidLoyaltyAccountStateError("LoyaltyAccount requiere customer_id")
        return cls(id=new_uuid(), customer_id=customer_id)

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def suspend(self, reason: str) -> None:
        if self.status is not AccountStatus.ACTIVE:
            raise InvalidLoyaltyAccountStateError(
                f"Solo se suspende una cuenta activa (actual: {self.status.value})")
        if not (reason or "").strip():
            raise InvalidLoyaltyAccountStateError("La suspensión requiere un motivo")
        self.status = AccountStatus.SUSPENDED
        self.suspended_at = _utcnow()
        self._touch()

    def reactivate(self) -> None:
        if self.status is not AccountStatus.SUSPENDED:
            raise InvalidLoyaltyAccountStateError(
                f"No se puede reactivar desde {self.status.value}")
        self.status = AccountStatus.ACTIVE
        self.suspended_at = None
        self._touch()

    def close(self, reason: str) -> None:
        if self.status is AccountStatus.CLOSED:
            raise InvalidLoyaltyAccountStateError("La cuenta ya está cerrada")
        if not (reason or "").strip():
            raise InvalidLoyaltyAccountStateError("El cierre requiere un motivo")
        self.status = AccountStatus.CLOSED
        self.closed_at = _utcnow()
        self._touch()

    def is_operational(self) -> bool:
        return self.status is AccountStatus.ACTIVE

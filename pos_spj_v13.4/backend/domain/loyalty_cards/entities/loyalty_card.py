"""LoyaltyCard — the base card record (master prompt §31: "La tarjeta no es
la cuenta"). `membership_id`/`customer_id` are stored as unchecked
references, never cross-validated against `backend.domain.loyalty`'s own
tables — same bounded-context-isolation convention already established by
Commercial Instruments' `CouponDefinition.source_program_id` (LOY-12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.loyalty_cards.enums import LoyaltyCardStatus, LoyaltyCardType
from backend.domain.loyalty_cards.exceptions import (
    InvalidLoyaltyCardError,
    InvalidLoyaltyCardStateError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class LoyaltyCard:
    id: str
    card_number: str
    card_type: LoyaltyCardType
    customer_id: str | None
    membership_id: str | None
    status: LoyaltyCardStatus = LoyaltyCardStatus.ISSUED
    issued_at: str = field(default_factory=_utcnow)
    activated_at: str | None = None
    blocked_at: str | None = None
    block_reason: str | None = None
    replaces_card_id: str | None = None
    replaced_by_card_id: str | None = None
    cancelled_at: str | None = None
    cancel_reason: str | None = None
    expires_at: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.card_number or not self.card_number.strip():
            raise InvalidLoyaltyCardError("card_number es obligatorio")
        if self.status is LoyaltyCardStatus.UNASSIGNED:
            if self.customer_id or self.membership_id:
                raise InvalidLoyaltyCardError(
                    "Una tarjeta sin asignar no tiene cliente ni membresía")
            return
        if not self.customer_id:
            raise InvalidLoyaltyCardError("customer_id es obligatorio")
        if not self.membership_id:
            raise InvalidLoyaltyCardError("membership_id es obligatorio")

    @classmethod
    def issue(cls, card_number: str, card_type: LoyaltyCardType, customer_id: str,
              membership_id: str, **kwargs) -> "LoyaltyCard":
        return cls(id=new_uuid(), card_number=card_number.strip(), card_type=card_type,
                    customer_id=customer_id, membership_id=membership_id, **kwargs)

    @classmethod
    def generate_unassigned(cls, card_number: str, card_type: LoyaltyCardType) -> "LoyaltyCard":
        """§44: tarjeta preimpresa — número y QR propios, sin cliente todavía."""
        return cls(id=new_uuid(), card_number=card_number.strip(), card_type=card_type,
                   customer_id=None, membership_id=None, status=LoyaltyCardStatus.UNASSIGNED)

    def assign(self, *, customer_id: str, membership_id: str) -> None:
        """§45: asignar es una operación explícita y única. Una tarjeta ya
        asignada NO se reasigna: si cambia de dueño, se cancela y se emite otra."""
        if self.status is not LoyaltyCardStatus.UNASSIGNED:
            raise InvalidLoyaltyCardStateError(
                f"Sólo se asigna una tarjeta sin asignar (actual: {self.status.value})")
        if not customer_id or not membership_id:
            raise InvalidLoyaltyCardError("La asignación requiere cliente y membresía")
        self.customer_id = customer_id
        self.membership_id = membership_id
        self.status = LoyaltyCardStatus.ISSUED
        self.updated_at = _utcnow()

    @classmethod
    def issue_replacement(cls, old_card: "LoyaltyCard", card_number: str) -> "LoyaltyCard":
        """§31: a lost/damaged card is replaced, never reused — a fresh
        `LoyaltyCard` row, linked both ways to the one it replaces."""
        return cls(
            id=new_uuid(), card_number=card_number.strip(), card_type=old_card.card_type,
            customer_id=old_card.customer_id, membership_id=old_card.membership_id,
            replaces_card_id=old_card.id)

    def activate(self) -> None:
        if self.status is not LoyaltyCardStatus.ISSUED:
            raise InvalidLoyaltyCardStateError(
                f"Solo se activa desde ISSUED (actual: {self.status.value})")
        self.status = LoyaltyCardStatus.ACTIVE
        self.activated_at = _utcnow()
        self.updated_at = _utcnow()

    def block(self, reason: str) -> None:
        if self.status is not LoyaltyCardStatus.ACTIVE:
            raise InvalidLoyaltyCardStateError(
                f"Solo se bloquea desde ACTIVE (actual: {self.status.value})")
        if not (reason or "").strip():
            raise InvalidLoyaltyCardStateError("El bloqueo requiere un motivo")
        self.status = LoyaltyCardStatus.BLOCKED
        self.blocked_at = _utcnow()
        self.block_reason = reason
        self.updated_at = _utcnow()

    def unblock(self) -> None:
        if self.status is not LoyaltyCardStatus.BLOCKED:
            raise InvalidLoyaltyCardStateError(
                f"Solo se desbloquea desde BLOCKED (actual: {self.status.value})")
        self.status = LoyaltyCardStatus.ACTIVE
        self.blocked_at = None
        self.block_reason = None
        self.updated_at = _utcnow()

    def mark_replaced(self, replacement_card_id: str) -> None:
        if self.status in (LoyaltyCardStatus.CANCELLED, LoyaltyCardStatus.REPLACED):
            raise InvalidLoyaltyCardStateError(
                f"No se puede reponer desde {self.status.value}")
        self.status = LoyaltyCardStatus.REPLACED
        self.replaced_by_card_id = replacement_card_id
        self.updated_at = _utcnow()

    def cancel(self, reason: str) -> None:
        if self.status in (LoyaltyCardStatus.CANCELLED, LoyaltyCardStatus.REPLACED):
            raise InvalidLoyaltyCardStateError(
                f"No se puede cancelar desde {self.status.value}")
        if not (reason or "").strip():
            raise InvalidLoyaltyCardStateError("La cancelación requiere un motivo")
        self.status = LoyaltyCardStatus.CANCELLED
        self.cancelled_at = _utcnow()
        self.cancel_reason = reason
        self.updated_at = _utcnow()

    def expire(self) -> None:
        if self.status not in (LoyaltyCardStatus.ISSUED, LoyaltyCardStatus.ACTIVE):
            raise InvalidLoyaltyCardStateError(
                f"No se puede expirar desde {self.status.value}")
        self.status = LoyaltyCardStatus.EXPIRED
        self.updated_at = _utcnow()

    def is_usable(self) -> bool:
        return self.status is LoyaltyCardStatus.ACTIVE

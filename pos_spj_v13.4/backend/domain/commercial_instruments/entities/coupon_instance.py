"""CouponInstance — one issued, usable coupon (master prompt §21's flow:
Validar → Reservar → Aplicar provisionalmente → Completar venta → Confirmar
redención; "No marcar redención antes de completar la venta").

Deliberate simplification, documented not hidden: ``issue()`` produces an
instance already in ``ACTIVE`` status rather than modeling a separate
manual-activation ceremony after ``ISSUED`` — every real coupon type named
in §21 (public code, automatic, personalized, birthday...) is usable
immediately once created in this codebase's actual flows; ``ISSUED`` stays
in the enum (§21's own literal vocabulary) for a future phase that adds a
real staged activation step (e.g. a mailed physical coupon), but nothing
here produces it today.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.commercial_instruments.enums import CouponInstanceStatus
from backend.domain.commercial_instruments.exceptions import (
    InvalidCouponInstanceStateError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CouponInstance:
    id: str
    definition_id: str
    code: str
    status: CouponInstanceStatus = CouponInstanceStatus.ACTIVE
    customer_id: str | None = None
    sale_id: str | None = None
    issued_at: str = field(default_factory=_utcnow)
    reserved_at: str | None = None
    redeemed_at: str | None = None
    closed_at: str | None = None
    closed_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.definition_id:
            raise InvalidCouponInstanceStateError("definition_id es obligatorio")
        if not self.code or not self.code.strip():
            raise InvalidCouponInstanceStateError("code es obligatorio")

    @classmethod
    def issue(cls, definition_id: str, code: str, *,
              customer_id: str | None = None) -> "CouponInstance":
        return cls(id=new_uuid(), definition_id=definition_id, code=code.strip(),
                   customer_id=customer_id)

    def reserve(self, sale_id: str) -> None:
        if self.status is not CouponInstanceStatus.ACTIVE:
            raise InvalidCouponInstanceStateError(
                f"Solo se reserva un cupón ACTIVE (actual: {self.status.value})")
        if not sale_id:
            raise InvalidCouponInstanceStateError("La reserva requiere sale_id")
        self.status = CouponInstanceStatus.RESERVED
        self.sale_id = sale_id
        self.reserved_at = _utcnow()

    def release(self) -> None:
        if self.status is not CouponInstanceStatus.RESERVED:
            raise InvalidCouponInstanceStateError(
                f"Solo se libera un cupón RESERVED (actual: {self.status.value})")
        self.status = CouponInstanceStatus.ACTIVE
        self.sale_id = None
        self.reserved_at = None

    def confirm_redemption(self) -> None:
        if self.status is not CouponInstanceStatus.RESERVED:
            raise InvalidCouponInstanceStateError(
                f"Solo se confirma un cupón RESERVED (actual: {self.status.value})")
        self.status = CouponInstanceStatus.REDEEMED
        self.redeemed_at = _utcnow()

    def cancel(self, reason: str) -> None:
        if self.status in (CouponInstanceStatus.REDEEMED, CouponInstanceStatus.CANCELLED):
            raise InvalidCouponInstanceStateError(
                f"No se puede cancelar desde {self.status.value}")
        if not (reason or "").strip():
            raise InvalidCouponInstanceStateError("La cancelación requiere un motivo")
        self.status = CouponInstanceStatus.CANCELLED
        self.closed_at = _utcnow()
        self.closed_reason = reason

    def expire(self) -> None:
        if self.status not in (CouponInstanceStatus.ISSUED, CouponInstanceStatus.ACTIVE):
            raise InvalidCouponInstanceStateError(
                f"No se puede expirar desde {self.status.value}")
        self.status = CouponInstanceStatus.EXPIRED
        self.closed_at = _utcnow()

    def block(self, reason: str) -> None:
        if self.status in (CouponInstanceStatus.REDEEMED, CouponInstanceStatus.CANCELLED,
                           CouponInstanceStatus.EXPIRED):
            raise InvalidCouponInstanceStateError(
                f"No se puede bloquear desde {self.status.value}")
        if not (reason or "").strip():
            raise InvalidCouponInstanceStateError("El bloqueo requiere un motivo")
        self.status = CouponInstanceStatus.BLOCKED
        self.closed_at = _utcnow()
        self.closed_reason = reason

    def is_usable(self) -> bool:
        return self.status is CouponInstanceStatus.ACTIVE

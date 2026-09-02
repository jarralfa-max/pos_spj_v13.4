"""VoucherInstance — one issued, usable voucher (master prompt §22).
Supports partial redemption, unlike `CouponInstance`.

Deliberately balance-agnostic: this entity never computes a Decimal sum
itself (that lives in `VoucherBalancePolicy`, replaying the ledger) — its
``mark_redeemed(fully=...)`` method takes the outcome as a caller-supplied
fact, since only the caller (a use case with repository access) can compute
the post-redemption balance."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.commercial_instruments.enums import VoucherInstanceStatus
from backend.domain.commercial_instruments.exceptions import InvalidVoucherInstanceStateError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

_OPEN_STATUSES = (VoucherInstanceStatus.ACTIVE, VoucherInstanceStatus.PARTIALLY_REDEEMED)


@dataclass(slots=True)
class VoucherInstance:
    id: str
    definition_id: str
    code: str
    status: VoucherInstanceStatus = VoucherInstanceStatus.ACTIVE
    customer_id: str | None = None
    sale_id: str | None = None
    issued_at: str = field(default_factory=_utcnow)
    expires_at: str | None = None
    closed_at: str | None = None
    closed_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.definition_id:
            raise InvalidVoucherInstanceStateError("definition_id es obligatorio")
        if not self.code or not self.code.strip():
            raise InvalidVoucherInstanceStateError("code es obligatorio")

    @classmethod
    def issue(cls, definition_id: str, code: str, *,
              customer_id: str | None = None, expires_at: str | None = None) -> "VoucherInstance":
        return cls(id=new_uuid(), definition_id=definition_id, code=code.strip(),
                   customer_id=customer_id, expires_at=expires_at)

    def reserve(self, sale_id: str) -> None:
        if self.status not in _OPEN_STATUSES:
            raise InvalidVoucherInstanceStateError(
                f"No se puede reservar desde {self.status.value}")
        if not sale_id:
            raise InvalidVoucherInstanceStateError("La reserva requiere sale_id")
        self.status = VoucherInstanceStatus.RESERVED
        self.sale_id = sale_id

    def release(self, *, restore_status: VoucherInstanceStatus) -> None:
        if self.status is not VoucherInstanceStatus.RESERVED:
            raise InvalidVoucherInstanceStateError(
                f"Solo se libera desde RESERVED (actual: {self.status.value})")
        if restore_status not in _OPEN_STATUSES:
            raise InvalidVoucherInstanceStateError(
                "restore_status debe ser ACTIVE o PARTIALLY_REDEEMED")
        self.status = restore_status
        self.sale_id = None

    def mark_redeemed(self, *, fully: bool) -> None:
        if self.status is not VoucherInstanceStatus.RESERVED:
            raise InvalidVoucherInstanceStateError(
                f"Solo se confirma desde RESERVED (actual: {self.status.value})")
        self.status = (VoucherInstanceStatus.REDEEMED if fully
                       else VoucherInstanceStatus.PARTIALLY_REDEEMED)
        self.sale_id = None

    def cancel(self, reason: str) -> None:
        if self.status in (VoucherInstanceStatus.REDEEMED, VoucherInstanceStatus.CANCELLED,
                          VoucherInstanceStatus.REVERSED):
            raise InvalidVoucherInstanceStateError(
                f"No se puede cancelar desde {self.status.value}")
        if not (reason or "").strip():
            raise InvalidVoucherInstanceStateError("La cancelación requiere un motivo")
        self.status = VoucherInstanceStatus.CANCELLED
        self.closed_at = _utcnow()
        self.closed_reason = reason

    def expire(self) -> None:
        if self.status not in (VoucherInstanceStatus.ISSUED, *_OPEN_STATUSES):
            raise InvalidVoucherInstanceStateError(
                f"No se puede expirar desde {self.status.value}")
        self.status = VoucherInstanceStatus.EXPIRED
        self.closed_at = _utcnow()

    def block(self, reason: str) -> None:
        if self.status in (VoucherInstanceStatus.REDEEMED, VoucherInstanceStatus.CANCELLED,
                          VoucherInstanceStatus.EXPIRED, VoucherInstanceStatus.REVERSED):
            raise InvalidVoucherInstanceStateError(
                f"No se puede bloquear desde {self.status.value}")
        if not (reason or "").strip():
            raise InvalidVoucherInstanceStateError("El bloqueo requiere un motivo")
        self.status = VoucherInstanceStatus.BLOCKED
        self.closed_at = _utcnow()
        self.closed_reason = reason

    def reverse(self, reason: str) -> None:
        if self.status is VoucherInstanceStatus.REVERSED:
            raise InvalidVoucherInstanceStateError("Ya fue reversado")
        if not (reason or "").strip():
            raise InvalidVoucherInstanceStateError("El reverso requiere un motivo")
        self.status = VoucherInstanceStatus.REVERSED
        self.closed_at = _utcnow()
        self.closed_reason = reason

    def is_usable(self) -> bool:
        return self.status in _OPEN_STATUSES

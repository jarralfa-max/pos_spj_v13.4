"""RedeliveryRequest (master prompt §41). Never silently reuses the same
failed attempt — a new delivery attempt only happens through an explicit
request that someone approves, with its own window/fee.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid, validate_uuidv7
from backend.domain.orders_delivery.enums import RedeliveryStatus
from backend.domain.orders_delivery.exceptions import InvalidRedeliveryStateError
from backend.domain.orders_delivery.value_objects.order_money import money


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class RedeliveryRequest:
    id: str
    original_delivery_job_id: str
    reason: str
    requested_by_user_id: str
    new_window_start: str | None = None
    new_window_end: str | None = None
    additional_fee: Decimal = Decimal("0")
    approved_by_user_id: str | None = None
    status: RedeliveryStatus = RedeliveryStatus.PENDING
    new_delivery_job_id: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls, *, original_delivery_job_id: str, reason: str, requested_by_user_id: str,
        new_window_start: str | None = None, new_window_end: str | None = None,
        additional_fee: Decimal = Decimal("0"),
    ) -> "RedeliveryRequest":
        validate_uuidv7(original_delivery_job_id)
        validate_uuidv7(requested_by_user_id)
        if not (reason or "").strip():
            raise InvalidRedeliveryStateError("La reentrega requiere un motivo")
        return cls(
            id=new_uuid(), original_delivery_job_id=original_delivery_job_id, reason=reason,
            requested_by_user_id=requested_by_user_id, new_window_start=new_window_start,
            new_window_end=new_window_end, additional_fee=money(additional_fee),
        )

    def approve(self, *, approved_by_user_id: str, new_delivery_job_id: str) -> None:
        if self.status != RedeliveryStatus.PENDING:
            raise InvalidRedeliveryStateError(
                f"No se puede aprobar una reentrega en estado {self.status.value}")
        validate_uuidv7(approved_by_user_id)
        validate_uuidv7(new_delivery_job_id)
        self.approved_by_user_id = approved_by_user_id
        self.new_delivery_job_id = new_delivery_job_id
        self.status = RedeliveryStatus.APPROVED
        self.updated_at = _now()

    def reject(self) -> None:
        if self.status != RedeliveryStatus.PENDING:
            raise InvalidRedeliveryStateError(
                f"No se puede rechazar una reentrega en estado {self.status.value}")
        self.status = RedeliveryStatus.REJECTED
        self.updated_at = _now()

    def complete(self) -> None:
        if self.status != RedeliveryStatus.APPROVED:
            raise InvalidRedeliveryStateError(
                f"No se puede completar una reentrega en estado {self.status.value}")
        self.status = RedeliveryStatus.COMPLETED
        self.updated_at = _now()

    def cancel(self) -> None:
        if self.status in (RedeliveryStatus.COMPLETED, RedeliveryStatus.CANCELLED):
            raise InvalidRedeliveryStateError(
                f"No se puede cancelar una reentrega en estado {self.status.value}")
        self.status = RedeliveryStatus.CANCELLED
        self.updated_at = _now()

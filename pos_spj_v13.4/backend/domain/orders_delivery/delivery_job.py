"""DeliveryJob (master prompt §31) — the last-mile execution aggregate,
DELIBERATELY SEPARATE from `CustomerOrder` (master prompt §5: Pedido ≠
Venta ≠ DeliveryJob). References `order_id`, never the reverse — an order
knows nothing about its delivery job's internal state, only its own
`FulfillmentStatus` (a future phase may project delivery events back onto
the order's fulfillment status, but this aggregate never reaches into
`CustomerOrder` directly).

Same `slots=True`/`create()`/`new_uuid()` shape as `CustomerOrder`. ORD-15
only wires `create()`/`assign_driver()`; the rest of the lifecycle methods
below exist because `DeliveryLifecyclePolicy` already defines the full
transition table (§32) and a later ORD-16-19 phase will call them — adding
the methods now avoids ORD-15 and ORD-18 disagreeing on the aggregate's own
shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid, validate_uuidv7
from backend.domain.orders_delivery.enums import DeliveryStatus, FailureReason
from backend.domain.orders_delivery.exceptions import (
    DeliveryDriverRequiredError,
    DeliveryEvidenceRequiredError,
    DeliveryFailureReasonRequiredError,
    InvalidDeliveryJobStateError,
)
from backend.domain.orders_delivery.policies.delivery_lifecycle_policy import (
    DeliveryLifecyclePolicy,
)
from backend.domain.orders_delivery.value_objects.delivery_evidence import DeliveryEvidence
from backend.domain.orders_delivery.value_objects.order_money import money


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class DeliveryAttempt:
    id: str
    delivery_job_id: str
    successful: bool
    evidence: DeliveryEvidence | None = None
    failure_reason: str | None = None
    attempted_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls, *, delivery_job_id: str, successful: bool,
        evidence: DeliveryEvidence | None = None, failure_reason: str | None = None,
        evidence_required: bool = True,
    ) -> "DeliveryAttempt":
        validate_uuidv7(delivery_job_id)
        if successful:
            if evidence_required and (evidence is None or evidence.is_empty):
                raise DeliveryEvidenceRequiredError(
                    "Una entrega exitosa requiere evidencia (receptor/firma/foto/PIN/geo)")
        else:
            if not (failure_reason or "").strip():
                raise DeliveryFailureReasonRequiredError("Un intento fallido requiere un motivo")
            try:
                FailureReason(failure_reason)
            except ValueError as exc:
                raise DeliveryFailureReasonRequiredError(
                    f"Motivo de falla desconocido: {failure_reason!r}") from exc
        return cls(id=new_uuid(), delivery_job_id=delivery_job_id, successful=successful,
                    evidence=evidence, failure_reason=failure_reason)


@dataclass(slots=True)
class DeliveryJob:
    id: str
    order_id: str
    branch_id: str
    delivery_number: str | None = None
    delivery_zone_id: str | None = None
    status: DeliveryStatus = DeliveryStatus.PENDING_ASSIGNMENT
    priority: str | None = None
    assigned_driver_id: str | None = None
    route_id: str | None = None
    scheduled_window_start: str | None = None
    scheduled_window_end: str | None = None
    estimated_arrival_at: str | None = None
    dispatched_at: str | None = None
    delivered_at: str | None = None
    failed_at: str | None = None
    delivery_fee: Decimal = Decimal("0")
    cash_to_collect: Decimal = Decimal("0")
    payment_method_expected: str | None = None
    operation_id: str | None = None
    attempts: list[DeliveryAttempt] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls, *, order_id: str, branch_id: str, operation_id: str,
        delivery_zone_id: str | None = None, priority: str | None = None,
        scheduled_window_start: str | None = None, scheduled_window_end: str | None = None,
        delivery_fee: Decimal = Decimal("0"), cash_to_collect: Decimal = Decimal("0"),
        payment_method_expected: str | None = None,
    ) -> "DeliveryJob":
        validate_uuidv7(order_id)
        validate_uuidv7(branch_id)
        return cls(
            id=new_uuid(), order_id=order_id, branch_id=branch_id,
            delivery_zone_id=delivery_zone_id, priority=priority,
            scheduled_window_start=scheduled_window_start,
            scheduled_window_end=scheduled_window_end,
            delivery_fee=money(delivery_fee), cash_to_collect=money(cash_to_collect),
            payment_method_expected=payment_method_expected, operation_id=operation_id,
        )

    def assign_driver(self, *, driver_id: str) -> None:
        """Assigning (or reassigning, before dispatch) a driver is always
        valid from PENDING_ASSIGNMENT or ASSIGNED — anything else (already
        dispatched, cancelled, ...) is a real conflict, checked directly
        rather than gamed through the transition table."""
        validate_uuidv7(driver_id)
        if self.status not in (DeliveryStatus.PENDING_ASSIGNMENT, DeliveryStatus.ASSIGNED):
            raise InvalidDeliveryJobStateError(
                f"No se puede asignar repartidor en estado {self.status.value}")
        self.assigned_driver_id = driver_id
        self.status = DeliveryStatus.ASSIGNED
        self.updated_at = _now()

    def mark_ready_to_dispatch(self) -> None:
        DeliveryLifecyclePolicy.ensure_transition(
            current=self.status, target=DeliveryStatus.READY_TO_DISPATCH)
        self.status = DeliveryStatus.READY_TO_DISPATCH
        self.updated_at = _now()

    def dispatch(self) -> None:
        if not self.assigned_driver_id:
            raise DeliveryDriverRequiredError("No se puede despachar sin repartidor asignado")
        DeliveryLifecyclePolicy.ensure_transition(
            current=self.status, target=DeliveryStatus.DISPATCHED)
        self.status = DeliveryStatus.DISPATCHED
        self.dispatched_at = _now()
        self.updated_at = _now()

    def mark_in_transit(self) -> None:
        DeliveryLifecyclePolicy.ensure_transition(
            current=self.status, target=DeliveryStatus.IN_TRANSIT)
        self.status = DeliveryStatus.IN_TRANSIT
        self.updated_at = _now()

    def mark_arrived(self) -> None:
        DeliveryLifecyclePolicy.ensure_transition(
            current=self.status, target=DeliveryStatus.ARRIVED)
        self.status = DeliveryStatus.ARRIVED
        self.updated_at = _now()

    def start_delivery_attempt(self) -> None:
        DeliveryLifecyclePolicy.ensure_transition(
            current=self.status, target=DeliveryStatus.DELIVERY_ATTEMPT)
        self.status = DeliveryStatus.DELIVERY_ATTEMPT
        self.updated_at = _now()

    def mark_delivered(self) -> None:
        DeliveryLifecyclePolicy.ensure_transition(
            current=self.status, target=DeliveryStatus.DELIVERED)
        self.status = DeliveryStatus.DELIVERED
        self.delivered_at = _now()
        self.updated_at = _now()

    def mark_failed(self) -> None:
        DeliveryLifecyclePolicy.ensure_transition(
            current=self.status, target=DeliveryStatus.FAILED)
        self.status = DeliveryStatus.FAILED
        self.failed_at = _now()
        self.updated_at = _now()

    def request_redelivery(self) -> None:
        DeliveryLifecyclePolicy.ensure_transition(
            current=self.status, target=DeliveryStatus.REDELIVERY_PENDING)
        self.status = DeliveryStatus.REDELIVERY_PENDING
        self.updated_at = _now()

    def start_return(self) -> None:
        DeliveryLifecyclePolicy.ensure_transition(
            current=self.status, target=DeliveryStatus.RETURNING)
        self.status = DeliveryStatus.RETURNING
        self.updated_at = _now()

    def complete_return(self) -> None:
        DeliveryLifecyclePolicy.ensure_transition(
            current=self.status, target=DeliveryStatus.RETURNED_TO_BRANCH)
        self.status = DeliveryStatus.RETURNED_TO_BRANCH
        self.updated_at = _now()

    def record_attempt(self, attempt: DeliveryAttempt) -> None:
        """§38-39: records the attempt and resolves the job's own status
        from its outcome — `DeliveryAttempt.create()` already validated
        evidence/failure-reason requirements before this is ever called."""
        if attempt.delivery_job_id != self.id:
            raise InvalidDeliveryJobStateError("El intento no pertenece a este job de entrega")
        self.attempts.append(attempt)
        if attempt.successful:
            self.mark_delivered()
        else:
            self.mark_failed()

    def cancel(self) -> None:
        DeliveryLifecyclePolicy.ensure_transition(
            current=self.status, target=DeliveryStatus.CANCELLED)
        self.status = DeliveryStatus.CANCELLED
        self.updated_at = _now()

    def close(self) -> None:
        DeliveryLifecyclePolicy.ensure_transition(
            current=self.status, target=DeliveryStatus.CLOSED)
        self.status = DeliveryStatus.CLOSED
        self.updated_at = _now()

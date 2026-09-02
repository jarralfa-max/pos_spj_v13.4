"""DriverOperationalProfile / DeliveryAssignment (master prompt §33-34).

Driver IDENTITY lives in RRHH/Usuarios (master prompt §33: "La identidad del
repartidor debe provenir de RRHH/Usuarios... Delivery no debe mantener una
tabla independiente de personas"). `DriverOperationalProfile` only tracks
the OPERATIONAL facts this bounded context needs (active/capacity/vehicle) —
`driver_id` is a foreign reference to that other identity, never validated
here (same "opaque cross-context id" pattern as `DeliveryZone.branch_id`).

`DeliveryAssignment` is the full propose→accept/reject audit trail, separate
from `DeliveryJob.assigned_driver_id` (a denormalized "who's currently on
it" field, ORD-15) — this entity is the "how did they get there" history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid, validate_uuidv7
from backend.domain.orders_delivery.enums import AssignmentStatus
from backend.domain.orders_delivery.exceptions import InvalidAssignmentStateError
from backend.domain.orders_delivery.value_objects.order_money import money


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class DriverOperationalProfile:
    id: str
    driver_id: str
    branch_id: str
    vehicle_type: str | None = None
    active: bool = True
    capacity: int = 1
    current_assignment_count: int = 0
    cash_limit: Decimal = Decimal("0")
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls, *, driver_id: str, branch_id: str, vehicle_type: str | None = None,
        capacity: int = 1, cash_limit: Decimal = Decimal("0"),
    ) -> "DriverOperationalProfile":
        validate_uuidv7(driver_id)
        validate_uuidv7(branch_id)
        return cls(
            id=new_uuid(), driver_id=driver_id, branch_id=branch_id,
            vehicle_type=vehicle_type, capacity=max(1, capacity),
            cash_limit=money(cash_limit),
        )

    @property
    def has_capacity(self) -> bool:
        return self.active and self.current_assignment_count < self.capacity

    def increment_assignments(self) -> None:
        self.current_assignment_count += 1
        self.updated_at = _now()

    def decrement_assignments(self) -> None:
        self.current_assignment_count = max(0, self.current_assignment_count - 1)
        self.updated_at = _now()

    def deactivate(self) -> None:
        self.active = False
        self.updated_at = _now()

    def activate(self) -> None:
        self.active = True
        self.updated_at = _now()


@dataclass(slots=True)
class DeliveryAssignment:
    id: str
    delivery_job_id: str
    driver_id: str
    assigned_by_user_id: str
    vehicle_id: str | None = None
    status: AssignmentStatus = AssignmentStatus.PROPOSED
    assigned_at: str = field(default_factory=_now)
    accepted_at: str | None = None
    released_at: str | None = None
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(
        cls, *, delivery_job_id: str, driver_id: str, assigned_by_user_id: str,
        vehicle_id: str | None = None,
    ) -> "DeliveryAssignment":
        validate_uuidv7(delivery_job_id)
        validate_uuidv7(driver_id)
        validate_uuidv7(assigned_by_user_id)
        return cls(
            id=new_uuid(), delivery_job_id=delivery_job_id, driver_id=driver_id,
            assigned_by_user_id=assigned_by_user_id, vehicle_id=vehicle_id,
        )

    def accept(self) -> None:
        if self.status != AssignmentStatus.PROPOSED:
            raise InvalidAssignmentStateError(
                f"No se puede aceptar una asignación en estado {self.status.value}")
        self.status = AssignmentStatus.ACCEPTED
        self.accepted_at = _now()
        self.updated_at = _now()

    def reject(self) -> None:
        if self.status != AssignmentStatus.PROPOSED:
            raise InvalidAssignmentStateError(
                f"No se puede rechazar una asignación en estado {self.status.value}")
        self.status = AssignmentStatus.REJECTED
        self.updated_at = _now()

    def activate(self) -> None:
        if self.status != AssignmentStatus.ACCEPTED:
            raise InvalidAssignmentStateError(
                f"No se puede activar una asignación en estado {self.status.value}")
        self.status = AssignmentStatus.ACTIVE
        self.updated_at = _now()

    def complete(self) -> None:
        if self.status != AssignmentStatus.ACTIVE:
            raise InvalidAssignmentStateError(
                f"No se puede completar una asignación en estado {self.status.value}")
        self.status = AssignmentStatus.COMPLETED
        self.released_at = _now()
        self.updated_at = _now()

    def cancel(self) -> None:
        if self.status in (AssignmentStatus.COMPLETED, AssignmentStatus.CANCELLED):
            raise InvalidAssignmentStateError(
                f"No se puede cancelar una asignación en estado {self.status.value}")
        self.status = AssignmentStatus.CANCELLED
        self.released_at = _now()
        self.updated_at = _now()

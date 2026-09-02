"""DeliveryRoute / DeliveryRouteStop (master prompt §35). Supports one or
many deliveries, sequencing, and per-stop ETA — deliberately basic (no
distance/time optimizer, per the master prompt's own instruction: "la
primera versión puede usar planificación básica").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.shared.ids import new_uuid, validate_uuidv7
from backend.domain.orders_delivery.enums import RouteStatus, RouteStopStatus
from backend.domain.orders_delivery.exceptions import InvalidRouteStopError
from backend.domain.orders_delivery.policies.route_policy import RoutePolicy


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class DeliveryRouteStop:
    id: str
    route_id: str
    delivery_job_id: str
    sequence: int
    status: RouteStopStatus = RouteStopStatus.PENDING
    estimated_arrival_at: str | None = None
    created_at: str = field(default_factory=_now)

    @classmethod
    def create(cls, *, route_id: str, delivery_job_id: str, sequence: int,
               estimated_arrival_at: str | None = None) -> "DeliveryRouteStop":
        validate_uuidv7(route_id)
        validate_uuidv7(delivery_job_id)
        if sequence < 1:
            raise InvalidRouteStopError("La secuencia debe ser mayor a cero")
        return cls(id=new_uuid(), route_id=route_id, delivery_job_id=delivery_job_id,
                    sequence=sequence, estimated_arrival_at=estimated_arrival_at)


@dataclass(slots=True)
class DeliveryRoute:
    id: str
    branch_id: str
    status: RouteStatus = RouteStatus.DRAFT
    assigned_driver_id: str | None = None
    stops: list[DeliveryRouteStop] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @classmethod
    def create(cls, *, branch_id: str) -> "DeliveryRoute":
        validate_uuidv7(branch_id)
        return cls(id=new_uuid(), branch_id=branch_id)

    def add_stop(self, *, delivery_job_id: str, sequence: int,
                 estimated_arrival_at: str | None = None) -> DeliveryRouteStop:
        RoutePolicy.ensure_can_add_stop(self.status)
        RoutePolicy.ensure_unique_sequence({s.sequence for s in self.stops}, sequence)
        stop = DeliveryRouteStop.create(
            route_id=self.id, delivery_job_id=delivery_job_id, sequence=sequence,
            estimated_arrival_at=estimated_arrival_at)
        self.stops.append(stop)
        self.updated_at = _now()
        return stop

    @property
    def ordered_stops(self) -> list[DeliveryRouteStop]:
        return sorted(self.stops, key=lambda s: s.sequence)

    def plan(self) -> None:
        if not self.stops:
            raise InvalidRouteStopError("Una ruta requiere al menos una parada para planificarse")
        RoutePolicy.ensure_transition(current=self.status, target=RouteStatus.PLANNED)
        self.status = RouteStatus.PLANNED
        self.updated_at = _now()

    def assign_driver(self, *, driver_id: str) -> None:
        validate_uuidv7(driver_id)
        RoutePolicy.ensure_transition(current=self.status, target=RouteStatus.ASSIGNED)
        self.assigned_driver_id = driver_id
        self.status = RouteStatus.ASSIGNED
        self.updated_at = _now()

    def activate(self) -> None:
        RoutePolicy.ensure_transition(current=self.status, target=RouteStatus.ACTIVE)
        self.status = RouteStatus.ACTIVE
        self.updated_at = _now()

    def complete(self) -> None:
        RoutePolicy.ensure_transition(current=self.status, target=RouteStatus.COMPLETED)
        self.status = RouteStatus.COMPLETED
        self.updated_at = _now()

    def cancel(self) -> None:
        RoutePolicy.ensure_transition(current=self.status, target=RouteStatus.CANCELLED)
        self.status = RouteStatus.CANCELLED
        self.updated_at = _now()

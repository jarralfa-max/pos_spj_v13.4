"""RoutePolicy (master prompt §35). Mirrors the enum-transition-table style
used everywhere else in this domain. "La primera versión puede usar
planificación básica" — this is sequencing/status validation only, no
distance/time optimization.
"""

from __future__ import annotations

from backend.domain.orders_delivery.enums import RouteStatus
from backend.domain.orders_delivery.exceptions import InvalidRouteStateError, InvalidRouteStopError


class RoutePolicy:
    TRANSITIONS = {
        (RouteStatus.DRAFT, RouteStatus.PLANNED),
        (RouteStatus.DRAFT, RouteStatus.CANCELLED),
        (RouteStatus.PLANNED, RouteStatus.ASSIGNED),
        (RouteStatus.PLANNED, RouteStatus.CANCELLED),
        (RouteStatus.ASSIGNED, RouteStatus.ACTIVE),
        (RouteStatus.ASSIGNED, RouteStatus.CANCELLED),
        (RouteStatus.ACTIVE, RouteStatus.COMPLETED),
        (RouteStatus.ACTIVE, RouteStatus.CANCELLED),
    }
    FINAL_STATUSES = frozenset({RouteStatus.COMPLETED, RouteStatus.CANCELLED})

    @classmethod
    def ensure_transition(cls, *, current: RouteStatus, target: RouteStatus) -> None:
        if current in cls.FINAL_STATUSES:
            raise InvalidRouteStateError("Final routes cannot transition")
        if (current, target) not in cls.TRANSITIONS:
            raise InvalidRouteStateError(
                f"Invalid route transition: {current.value} -> {target.value}")

    @staticmethod
    def ensure_can_add_stop(status: RouteStatus) -> None:
        """Only DRAFT accepts new stops — once `plan()` runs the sequence is
        considered fixed (no re-planning support yet, per the master
        prompt's own "planificación básica" scope for this phase)."""
        if status != RouteStatus.DRAFT:
            raise InvalidRouteStopError(
                f"No se pueden agregar paradas a una ruta en estado {status.value}")

    @staticmethod
    def ensure_unique_sequence(existing_sequences: set[int], sequence: int) -> None:
        if sequence in existing_sequences:
            raise InvalidRouteStopError(f"Ya existe una parada con secuencia {sequence}")

"""OrderPreparationPolicy (master prompt §25). Enum-transition-table style,
mirrors `OrderLifecyclePolicy`/`ScheduledOrderPolicy` exactly.
"""

from __future__ import annotations

from backend.domain.orders_delivery.enums import FulfillmentStatus, PreparationStatus
from backend.domain.orders_delivery.exceptions import OrderPreparationNotAllowedError


class OrderPreparationPolicy:
    TRANSITIONS = {
        (PreparationStatus.PENDING, PreparationStatus.ASSIGNED),
        (PreparationStatus.ASSIGNED, PreparationStatus.IN_PROGRESS),
        (PreparationStatus.IN_PROGRESS, PreparationStatus.PARTIALLY_PREPARED),
        (PreparationStatus.IN_PROGRESS, PreparationStatus.PENDING_WEIGHT),
        (PreparationStatus.IN_PROGRESS, PreparationStatus.PENDING_CUSTOMER_APPROVAL),
        (PreparationStatus.PARTIALLY_PREPARED, PreparationStatus.IN_PROGRESS),
        (PreparationStatus.PENDING_WEIGHT, PreparationStatus.IN_PROGRESS),
        (PreparationStatus.PENDING_CUSTOMER_APPROVAL, PreparationStatus.IN_PROGRESS),
        (PreparationStatus.IN_PROGRESS, PreparationStatus.READY),
        (PreparationStatus.PARTIALLY_PREPARED, PreparationStatus.READY),
        (PreparationStatus.PENDING, PreparationStatus.CANCELLED),
        (PreparationStatus.ASSIGNED, PreparationStatus.CANCELLED),
        (PreparationStatus.IN_PROGRESS, PreparationStatus.CANCELLED),
    }
    FINAL_STATUSES = frozenset({PreparationStatus.READY, PreparationStatus.CANCELLED})

    @classmethod
    def ensure_transition(cls, *, current: PreparationStatus, target: PreparationStatus) -> None:
        if current in cls.FINAL_STATUSES:
            raise OrderPreparationNotAllowedError(
                f"La preparación en estado {current.value} no puede transicionar")
        if (current, target) not in cls.TRANSITIONS:
            raise OrderPreparationNotAllowedError(
                f"Transición de preparación inválida: {current.value} -> {target.value}")

    @staticmethod
    def ensure_reserved_before_preparation(fulfillment_status: FulfillmentStatus) -> None:
        """§25: preparation can only start once Inventory has confirmed the
        reservation (ORD-8) — never against a PENDING/FAILED fulfillment."""
        if fulfillment_status != FulfillmentStatus.RESERVED:
            raise OrderPreparationNotAllowedError(
                "El pedido debe tener inventario reservado antes de iniciar preparación")

"""DeliveryJob lifecycle invariants (master prompt §32). Mirrors
`OrderLifecyclePolicy` exactly — enum-transition-table style. Covers the
FULL `DeliveryStatus` enum now (§32) even though ORD-15 only wires
CREATE/ASSIGN use cases; ORD-16-19 reuse this same table for
dispatch/delivery/failure/return, never inventing a second one.
"""

from __future__ import annotations

from backend.domain.orders_delivery.enums import DeliveryStatus
from backend.domain.orders_delivery.exceptions import InvalidDeliveryJobStateError


class DeliveryLifecyclePolicy:
    # Only states with NO valid outgoing transition belong here — DELIVERED
    # still moves on to CLOSED (same reasoning as `OrderLifecyclePolicy`
    # deliberately excluding COMPLETED: a status can be "done" for most
    # purposes yet still have one legitimate next step). RETURNED_TO_BRANCH
    # has no entry in TRANSITIONS either, so leaving it out here changes
    # nothing observable — it still rejects via the TRANSITIONS lookup.
    FINAL_STATUSES = frozenset({DeliveryStatus.CANCELLED, DeliveryStatus.CLOSED})

    TRANSITIONS = {
        (DeliveryStatus.PENDING_ASSIGNMENT, DeliveryStatus.ASSIGNED),
        (DeliveryStatus.PENDING_ASSIGNMENT, DeliveryStatus.CANCELLED),
        (DeliveryStatus.ASSIGNED, DeliveryStatus.PENDING_ASSIGNMENT),  # driver declines/reassign
        (DeliveryStatus.ASSIGNED, DeliveryStatus.READY_TO_DISPATCH),
        (DeliveryStatus.ASSIGNED, DeliveryStatus.CANCELLED),
        (DeliveryStatus.READY_TO_DISPATCH, DeliveryStatus.DISPATCHED),
        (DeliveryStatus.READY_TO_DISPATCH, DeliveryStatus.CANCELLED),
        (DeliveryStatus.DISPATCHED, DeliveryStatus.IN_TRANSIT),
        (DeliveryStatus.IN_TRANSIT, DeliveryStatus.ARRIVED),
        (DeliveryStatus.ARRIVED, DeliveryStatus.DELIVERY_ATTEMPT),
        (DeliveryStatus.DELIVERY_ATTEMPT, DeliveryStatus.DELIVERED),
        (DeliveryStatus.DELIVERY_ATTEMPT, DeliveryStatus.FAILED),
        (DeliveryStatus.FAILED, DeliveryStatus.REDELIVERY_PENDING),
        (DeliveryStatus.FAILED, DeliveryStatus.RETURNING),
        (DeliveryStatus.REDELIVERY_PENDING, DeliveryStatus.READY_TO_DISPATCH),
        (DeliveryStatus.RETURNING, DeliveryStatus.RETURNED_TO_BRANCH),
        (DeliveryStatus.DELIVERED, DeliveryStatus.CLOSED),
    }

    @classmethod
    def normalize(cls, status: DeliveryStatus | str) -> DeliveryStatus:
        if isinstance(status, DeliveryStatus):
            return status
        try:
            return DeliveryStatus(str(status))
        except ValueError as exc:
            raise InvalidDeliveryJobStateError(f"Unknown delivery status: {status}") from exc

    @classmethod
    def ensure_transition(cls, *, current: DeliveryStatus | str,
                           target: DeliveryStatus | str) -> None:
        current_status, target_status = cls.normalize(current), cls.normalize(target)
        if current_status in cls.FINAL_STATUSES:
            raise InvalidDeliveryJobStateError("Final delivery jobs cannot transition")
        if (current_status, target_status) not in cls.TRANSITIONS:
            raise InvalidDeliveryJobStateError(
                f"Invalid delivery transition: {current_status.value} -> {target_status.value}")

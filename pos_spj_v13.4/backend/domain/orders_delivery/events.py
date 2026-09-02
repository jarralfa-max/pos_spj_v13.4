"""Canonical Pedidos/Delivery event names and payload contract (master
prompt §59). Mirrors backend/domain/sales/events.py's `SaleEvents`/
`sale_event_payload()` shape exactly.

This is the TARGET single canonical vocabulary for the whole bounded context
going forward — it exists specifically to resolve the "event vocabulary
triplication" blocker `docs/refactor/orders_delivery_legacy_inventory.md` §2
flagged before ORD-2: three parallel catalogs (`core/events/event_bus.py`
constants, `core/delivery/domain/events.py`'s `DeliveryEvents` StrEnum, and a
nascent `backend/shared/events/event_names.py` subset) coexist today, bridged
manually via `core/delivery/application/legacy_event_bridge.py`.

It is NOT wired into the real, running EventBus in this phase — the legacy
vocabularies keep driving `core/delivery/` (which still backs the live
`modulos/delivery.py` UI) until a future phase migrates real use cases onto
the `CustomerOrder`/`DeliveryJob` aggregates built here. Do not assume
publishing `OrderEvents.CREATED` etc. has any real subscriber yet — confirmed
none exists as of ORD-2.

ORD-2 scope: only the Order-side events a pure `CustomerOrder` aggregate
raises. Delivery-side events (DELIVERY_JOB_CREATED, DELIVERY_DISPATCHED,
etc. — §59's second block) are added in ORD-15+ once the separate
`DeliveryJob` aggregate exists.
"""
from datetime import datetime, timezone

from backend.shared.ids import new_uuid, validate_uuidv7


class OrderEvents:
    CREATED = "ORDER_CREATED"
    CONFIRMED = "ORDER_CONFIRMED"
    SCHEDULED = "ORDER_SCHEDULED"
    SCHEDULE_ACTIVATED = "ORDER_SCHEDULE_ACTIVATED"
    RESERVATION_REQUESTED = "ORDER_RESERVATION_REQUESTED"
    RESERVED = "ORDER_RESERVED"
    RESERVATION_FAILED = "ORDER_RESERVATION_FAILED"
    PREPARATION_STARTED = "ORDER_PREPARATION_STARTED"
    ITEM_WEIGHT_ADJUSTED = "ORDER_ITEM_WEIGHT_ADJUSTED"
    CUSTOMER_APPROVAL_REQUIRED = "ORDER_CUSTOMER_APPROVAL_REQUIRED"
    CUSTOMER_ADJUSTMENT_ACCEPTED = "ORDER_CUSTOMER_ADJUSTMENT_ACCEPTED"
    CUSTOMER_ADJUSTMENT_REJECTED = "ORDER_CUSTOMER_ADJUSTMENT_REJECTED"
    SUBSTITUTION_PROPOSED = "ORDER_SUBSTITUTION_PROPOSED"
    SUBSTITUTION_ACCEPTED = "ORDER_SUBSTITUTION_ACCEPTED"
    SUBSTITUTION_REJECTED = "ORDER_SUBSTITUTION_REJECTED"
    READY = "ORDER_READY"
    CANCELLED = "ORDER_CANCELLED"
    CLOSED = "ORDER_CLOSED"
    REVERSED = "ORDER_REVERSED"
    SALE_PROJECTED = "ORDER_SALE_PROJECTED"
    PAYMENT_RECORDED = "ORDER_PAYMENT_RECORDED"
    REFUNDED = "ORDER_REFUNDED"


ALL_ORDER_EVENTS = frozenset(
    value for name, value in vars(OrderEvents).items()
    if name.isupper() and isinstance(value, str)
)


def order_event_payload(event_name: str, *, operation_id: str, entity_id: str,
                         branch_id: str, user_id: str, **payload: object) -> dict[str, object]:
    if event_name not in ALL_ORDER_EVENTS:
        raise ValueError(f"Unknown canonical Order event: {event_name}")
    for value in (operation_id, entity_id, branch_id, user_id):
        validate_uuidv7(value)
    event_id = new_uuid()
    if event_id in {operation_id, entity_id}:
        raise ValueError("event_id, operation_id and entity_id must be distinct")
    return {
        "event_id": event_id,
        "event_name": event_name,
        "operation_id": operation_id,
        "entity_id": entity_id,
        "branch_id": branch_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": "orders_delivery",
        "payload": payload,
    }


class DeliveryEvents:
    """§59's second block — DeliveryJob-side events, ORD-15+. Same target-
    vocabulary status as `OrderEvents`: not wired to the live EventBus yet.
    """

    JOB_CREATED = "DELIVERY_JOB_CREATED"
    DRIVER_ASSIGNED = "DELIVERY_DRIVER_ASSIGNED"
    ROUTE_ASSIGNED = "DELIVERY_ROUTE_ASSIGNED"
    DISPATCHED = "DELIVERY_DISPATCHED"
    OUT_FOR_DELIVERY = "DELIVERY_OUT_FOR_DELIVERY"
    ARRIVED = "DELIVERY_ARRIVED"
    ATTEMPT_STARTED = "DELIVERY_ATTEMPT_STARTED"
    COMPLETED = "DELIVERY_COMPLETED"
    FAILED = "DELIVERY_FAILED"
    REDELIVERY_REQUESTED = "DELIVERY_REDELIVERY_REQUESTED"
    RETURNED_TO_BRANCH = "DELIVERY_RETURNED_TO_BRANCH"
    CANCELLED = "DELIVERY_CANCELLED"
    CLOSED = "DELIVERY_CLOSED"
    CASH_COLLECTION_RECORDED = "DELIVERY_CASH_COLLECTION_RECORDED"
    DRIVER_SETTLEMENT_CREATED = "DRIVER_SETTLEMENT_CREATED"
    DRIVER_SETTLEMENT_DIFFERENCE_DETECTED = "DRIVER_SETTLEMENT_DIFFERENCE_DETECTED"
    DRIVER_SETTLEMENT_CLOSED = "DRIVER_SETTLEMENT_CLOSED"


ALL_DELIVERY_EVENTS = frozenset(
    value for name, value in vars(DeliveryEvents).items()
    if name.isupper() and isinstance(value, str)
)


def delivery_event_payload(event_name: str, *, operation_id: str, entity_id: str,
                            branch_id: str, user_id: str, **payload: object) -> dict[str, object]:
    if event_name not in ALL_DELIVERY_EVENTS:
        raise ValueError(f"Unknown canonical Delivery event: {event_name}")
    for value in (operation_id, entity_id, branch_id, user_id):
        validate_uuidv7(value)
    event_id = new_uuid()
    if event_id in {operation_id, entity_id}:
        raise ValueError("event_id, operation_id and entity_id must be distinct")
    return {
        "event_id": event_id,
        "event_name": event_name,
        "operation_id": operation_id,
        "entity_id": entity_id,
        "branch_id": branch_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": "orders_delivery",
        "payload": payload,
    }

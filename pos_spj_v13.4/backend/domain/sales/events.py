"""Canonical Sale/POS event names and payload contract (master prompt §60).
Mirrors backend/domain/cash_register/events.py's `CashEvents`/
`cash_event_payload()` shape exactly.

This is the TARGET vocabulary for the future Sale aggregate/use cases — it is
NOT wired into the real, running EventBus in this phase. The legacy events
already wired today (`core/events/domain_events.py`: `VENTA_COMPLETADA`
aliased as `SALE_CREATED`, `VENTA_CANCELADA`, `VENTA_SUSPENDIDA`,
`SALE_ITEMS_PROCESS`, ...) keep driving production
(`core/services/sales_service.py`, `core/events/wiring.py` subscribers) until
a future phase migrates real use cases onto the `Sale` aggregate built here.
Do not assume publishing `SaleEvents.STARTED` etc. has any real subscriber
yet — confirmed none exists as of SALES-3.
"""
from datetime import datetime, timezone

from backend.shared.ids import new_uuid, validate_uuidv7


class SaleEvents:
    STARTED = "SALE_STARTED"
    LINE_ADDED = "SALE_LINE_ADDED"
    LINE_UPDATED = "SALE_LINE_UPDATED"
    LINE_REMOVED = "SALE_LINE_REMOVED"
    CUSTOMER_ASSIGNED = "SALE_CUSTOMER_ASSIGNED"
    DISCOUNT_APPLIED = "SALE_DISCOUNT_APPLIED"
    SUSPENDED = "SALE_SUSPENDED"
    RESUMED = "SALE_RESUMED"
    CHECKOUT_STARTED = "SALE_CHECKOUT_STARTED"
    PAYMENT_PENDING = "SALE_PAYMENT_PENDING"
    PAYMENT_RECORDED = "SALE_PAYMENT_RECORDED"
    PAYMENT_CONFIRMED = "SALE_PAYMENT_CONFIRMED"
    LOYALTY_REDEEMED = "SALE_LOYALTY_REDEEMED"
    COMPLETED = "SALE_COMPLETED"
    CANCELLED = "SALE_CANCELLED"
    RETURNED = "SALE_RETURNED"
    REVERSED = "SALE_REVERSED"
    RECEIPT_REQUESTED = "SALE_RECEIPT_REQUESTED"
    RECEIPT_REPRINT_REQUESTED = "SALE_RECEIPT_REPRINT_REQUESTED"
    INVOICE_REQUESTED = "SALE_INVOICE_REQUESTED"
    INVOICE_ISSUED = "SALE_INVOICE_ISSUED"
    INVOICE_ERROR = "SALE_INVOICE_ERROR"


ALL_SALE_EVENTS = frozenset(
    value for name, value in vars(SaleEvents).items()
    if name.isupper() and isinstance(value, str)
)


def sale_event_payload(event_name: str, *, operation_id: str, entity_id: str,
                        branch_id: str, user_id: str, **payload: object) -> dict[str, object]:
    if event_name not in ALL_SALE_EVENTS:
        raise ValueError(f"Unknown canonical Sale event: {event_name}")
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
        "source_module": "sales",
        "payload": payload,
    }

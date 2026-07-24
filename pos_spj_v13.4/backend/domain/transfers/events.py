"""Canonical post-commit transfer event contract."""
from datetime import datetime, timezone
from backend.shared.ids import new_uuid


class TransferEvents:
    REQUEST_CREATED = "TRANSFER_REQUEST_CREATED"; REQUEST_SUBMITTED = "TRANSFER_REQUEST_SUBMITTED"
    APPROVED = "TRANSFER_APPROVED"; REJECTED = "TRANSFER_REJECTED"; RESERVED = "TRANSFER_RESERVED"
    ALLOCATED = "TRANSFER_ALLOCATED"; PICKING_STARTED = "TRANSFER_PICKING_STARTED"; PICKED = "TRANSFER_PICKED"
    READY_TO_DISPATCH = "TRANSFER_READY_TO_DISPATCH"; SHIPMENT_CREATED = "TRANSFER_SHIPMENT_CREATED"
    DISPATCHED = "TRANSFER_DISPATCHED"; IN_TRANSIT = "TRANSFER_IN_TRANSIT"; ARRIVED = "TRANSFER_ARRIVED"
    RECEIPT_STARTED = "TRANSFER_RECEIPT_STARTED"; PARTIALLY_RECEIVED = "TRANSFER_PARTIALLY_RECEIVED"
    RECEIVED = "TRANSFER_RECEIVED"; DIFFERENCE_DETECTED = "TRANSFER_DIFFERENCE_DETECTED"
    DIFFERENCE_RESOLVED = "TRANSFER_DIFFERENCE_RESOLVED"
    DIFFERENCE_CONFIRMED = "TRANSFER_DIFFERENCE_CONFIRMED"; LOSS_CONFIRMED = "TRANSFER_LOSS_CONFIRMED"
    RETURN_CREATED = "TRANSFER_RETURN_CREATED"
    RETURN_COMPLETED = "TRANSFER_RETURN_COMPLETED"; CANCELLED = "TRANSFER_CANCELLED"; REVERSED = "TRANSFER_REVERSED"
    SUGGESTION_CREATED = "TRANSFER_SUGGESTION_CREATED"
    CRITICAL_ALERT_CREATED = "TRANSFER_CRITICAL_ALERT_CREATED"
    WHATSAPP_ALERT_SENT = "TRANSFER_WHATSAPP_ALERT_SENT"


def event_payload(event_name: str, *, operation_id: str, entity_id: str, user_id: str, **extra: object) -> dict[str, object]:
    if event_name not in ALL_TRANSFER_EVENTS:
        raise ValueError(f"Unknown canonical transfer event: {event_name}")
    if not operation_id or not entity_id or not user_id:
        raise ValueError("Transfer event requires operation, entity, and user IDs")
    return {"event_id": new_uuid(), "event_name": event_name, "operation_id": operation_id,
            "entity_id": entity_id, "user_id": user_id, "source_module": "transfers",
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), **extra}


ALL_TRANSFER_EVENTS = frozenset(
    value for name, value in vars(TransferEvents).items()
    if name.isupper() and isinstance(value, str)
)

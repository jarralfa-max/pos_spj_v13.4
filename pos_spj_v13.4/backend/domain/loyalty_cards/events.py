"""Canonical Loyalty Cards event names and payload contract (LOY-16, master
prompt §31-32, §55/§62). Mirrors
``backend/domain/sweepstakes/events.py``'s shape. No existing Finance/other
handler vocabulary to align with (confirmed via grep before writing) —
Loyalty-Cards-only vocabulary."""
from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid, validate_uuidv7


class LoyaltyCardEvents:
    CARD_ISSUED = "LOYALTY_CARD_ISSUED"
    CARD_ACTIVATED = "LOYALTY_CARD_ACTIVATED"
    CARD_BLOCKED = "LOYALTY_CARD_BLOCKED"
    CARD_UNBLOCKED = "LOYALTY_CARD_UNBLOCKED"
    CARD_REPLACED = "LOYALTY_CARD_REPLACED"
    CARD_CANCELLED = "LOYALTY_CARD_CANCELLED"
    CARD_EXPIRED = "LOYALTY_CARD_EXPIRED"
    TOKEN_ROTATED = "LOYALTY_CARD_TOKEN_ROTATED"
    TOKEN_REVOKED = "LOYALTY_CARD_TOKEN_REVOKED"

    TEMPLATE_CREATED = "LOYALTY_CARD_TEMPLATE_CREATED"
    TEMPLATE_APPROVED = "LOYALTY_CARD_TEMPLATE_APPROVED"
    TEMPLATE_ACTIVATED = "LOYALTY_CARD_TEMPLATE_ACTIVATED"
    TEMPLATE_ARCHIVED = "LOYALTY_CARD_TEMPLATE_ARCHIVED"
    TEMPLATE_VERSION_CREATED = "LOYALTY_CARD_TEMPLATE_VERSION_CREATED"
    TEMPLATE_VERSION_APPROVED = "LOYALTY_CARD_TEMPLATE_VERSION_APPROVED"
    TEMPLATE_VERSION_ACTIVATED = "LOYALTY_CARD_TEMPLATE_VERSION_ACTIVATED"

    SHEET_PROFILE_CREATED = "LOYALTY_CARD_SHEET_PROFILE_CREATED"
    IMPOSITION_PROFILE_CREATED = "LOYALTY_CARD_IMPOSITION_PROFILE_CREATED"

    BATCH_CREATED = "LOYALTY_CARD_BATCH_CREATED"
    BATCH_APPROVED = "LOYALTY_CARD_BATCH_APPROVED"
    BATCH_PRINTING_STARTED = "LOYALTY_CARD_BATCH_PRINTING_STARTED"
    BATCH_COMPLETED = "LOYALTY_CARD_BATCH_COMPLETED"
    BATCH_CANCELLED = "LOYALTY_CARD_BATCH_CANCELLED"
    BATCH_ITEM_PRINTED = "LOYALTY_CARD_BATCH_ITEM_PRINTED"
    BATCH_ITEM_FAILED = "LOYALTY_CARD_BATCH_ITEM_FAILED"


ALL_LOYALTY_CARD_EVENTS = frozenset(
    value for name, value in vars(LoyaltyCardEvents).items()
    if name.isupper() and isinstance(value, str)
)


def loyalty_card_event_payload(
    event_name: str, *, operation_id: str, entity_id: str, branch_id: str, user_id: str,
    **payload: object,
) -> dict[str, object]:
    if event_name not in ALL_LOYALTY_CARD_EVENTS:
        raise ValueError(f"Unknown canonical Loyalty Card event: {event_name}")
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
        "source_module": "loyalty_cards",
        "payload": payload,
    }

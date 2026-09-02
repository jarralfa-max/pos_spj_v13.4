"""Canonical Customer Display domain events — SET-17. Mirrors
backend/domain/document_output/events.py's shape. All post-commit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class CustomerDisplayEvents:
    DISPLAY_REGISTERED = "CUSTOMER_DISPLAY_REGISTERED"
    DISPLAY_ACTIVATED = "CUSTOMER_DISPLAY_ACTIVATED"
    DISPLAY_DEACTIVATED = "CUSTOMER_DISPLAY_DEACTIVATED"
    DISPLAY_MODE_CHANGED = "CUSTOMER_DISPLAY_MODE_CHANGED"
    LAYOUT_ACTIVATED = "DISPLAY_LAYOUT_ACTIVATED"

    CAMPAIGN_SUBMITTED_FOR_APPROVAL = "CONTENT_CAMPAIGN_SUBMITTED_FOR_APPROVAL"
    CAMPAIGN_APPROVED = "CONTENT_CAMPAIGN_APPROVED"
    CAMPAIGN_REJECTED = "CONTENT_CAMPAIGN_REJECTED"
    CAMPAIGN_ACTIVATED = "CONTENT_CAMPAIGN_ACTIVATED"
    CAMPAIGN_PLACED = "CONTENT_CAMPAIGN_PLACED"
    CAMPAIGN_UNPLACED = "CONTENT_CAMPAIGN_UNPLACED"


ALL_CUSTOMER_DISPLAY_EVENTS = frozenset(
    value for key, value in vars(CustomerDisplayEvents).items()
    if not key.startswith("_") and isinstance(value, str)
)


def build_event_payload(
    event_name: str, *, operation_id: str, display_id: str | None = None,
    layout_id: str | None = None, user_id: str | None = None,
    source_module: str = "customer_display", **extra,
) -> dict:
    """Build the canonical minimum payload for a Customer Display event."""
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "display_id": display_id,
        "layout_id": layout_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload

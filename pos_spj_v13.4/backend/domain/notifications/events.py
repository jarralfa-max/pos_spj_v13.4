"""Canonical Notifications domain events — SET-20. Mirrors
backend/domain/integrations/events.py's shape. All post-commit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class NotificationsEvents:
    ACCOUNT_PROVISIONED = "NOTIFICATION_ACCOUNT_PROVISIONED"
    ACCOUNT_ACTIVATED = "NOTIFICATION_ACCOUNT_ACTIVATED"
    ACCOUNT_DEACTIVATED = "NOTIFICATION_ACCOUNT_DEACTIVATED"
    TEMPLATE_REGISTERED = "NOTIFICATION_TEMPLATE_REGISTERED"
    ROUTE_REGISTERED = "NOTIFICATION_ROUTE_REGISTERED"
    MESSAGE_SENT = "NOTIFICATION_MESSAGE_SENT"
    MESSAGE_FAILED = "NOTIFICATION_MESSAGE_FAILED"


ALL_NOTIFICATIONS_EVENTS = frozenset(
    value for key, value in vars(NotificationsEvents).items()
    if not key.startswith("_") and isinstance(value, str)
)


def build_event_payload(
    event_name: str, *, operation_id: str, account_id: str | None = None,
    template_id: str | None = None, route_id: str | None = None, user_id: str | None = None,
    source_module: str = "notifications", **extra,
) -> dict:
    """Build the canonical minimum payload for a Notifications event."""
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "account_id": account_id,
        "template_id": template_id,
        "route_id": route_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload

"""Canonical Integrations domain events — SET-19. Mirrors
backend/domain/customer_display/events.py's shape. All post-commit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class IntegrationsEvents:
    DEFINITION_REGISTERED = "INTEGRATION_DEFINITION_REGISTERED"
    INSTANCE_PROVISIONED = "INTEGRATION_INSTANCE_PROVISIONED"
    INSTANCE_ACTIVATED = "INTEGRATION_INSTANCE_ACTIVATED"
    INSTANCE_DEACTIVATED = "INTEGRATION_INSTANCE_DEACTIVATED"
    HEALTH_CHECK_RECORDED = "INTEGRATION_HEALTH_CHECK_RECORDED"
    WEBHOOK_REGISTERED = "WEBHOOK_ENDPOINT_REGISTERED"
    WEBHOOK_RECEIVED = "WEBHOOK_ENDPOINT_RECEIVED"


ALL_INTEGRATIONS_EVENTS = frozenset(
    value for key, value in vars(IntegrationsEvents).items()
    if not key.startswith("_") and isinstance(value, str)
)


def build_event_payload(
    event_name: str, *, operation_id: str, definition_id: str | None = None,
    instance_id: str | None = None, endpoint_id: str | None = None, user_id: str | None = None,
    source_module: str = "integrations", **extra,
) -> dict:
    """Build the canonical minimum payload for an Integrations event."""
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "definition_id": definition_id,
        "instance_id": instance_id,
        "endpoint_id": endpoint_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload

"""Canonical Feature Flags domain events — SET-21. Mirrors
backend/domain/notifications/events.py's shape. All post-commit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class FeatureFlagsEvents:
    FLAG_REGISTERED = "FEATURE_FLAG_REGISTERED"
    CHANGE_REQUESTED = "FEATURE_FLAG_CHANGE_REQUESTED"
    CHANGE_APPROVED = "FEATURE_FLAG_CHANGE_APPROVED"
    CHANGE_REJECTED = "FEATURE_FLAG_CHANGE_REJECTED"
    CHANGE_APPLIED = "FEATURE_FLAG_CHANGE_APPLIED"


ALL_FEATURE_FLAGS_EVENTS = frozenset(
    value for key, value in vars(FeatureFlagsEvents).items()
    if not key.startswith("_") and isinstance(value, str)
)


def build_event_payload(
    event_name: str, *, operation_id: str, flag_id: str | None = None, rule_id: str | None = None,
    change_request_id: str | None = None, user_id: str | None = None,
    source_module: str = "feature_flags", **extra,
) -> dict:
    """Build the canonical minimum payload for a Feature Flags event."""
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "flag_id": flag_id,
        "rule_id": rule_id,
        "change_request_id": change_request_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload

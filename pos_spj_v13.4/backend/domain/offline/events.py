"""Canonical Offline domain events — SET-23. Mirrors
backend/domain/appearance/events.py's shape. All post-commit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class OfflineEvents:
    CACHE_ENTRY_REFRESHED = "OFFLINE_CACHE_ENTRY_REFRESHED"
    CACHE_ENTRY_MARKED_STALE = "OFFLINE_CACHE_ENTRY_MARKED_STALE"
    CACHE_EXPIRATION_POLICY_REGISTERED = "OFFLINE_CACHE_EXPIRATION_POLICY_REGISTERED"


ALL_OFFLINE_EVENTS = frozenset(
    value for key, value in vars(OfflineEvents).items()
    if not key.startswith("_") and isinstance(value, str)
)


def build_event_payload(
    event_name: str, *, operation_id: str, cache_entry_id: str | None = None,
    expiration_policy_id: str | None = None, workstation_id: str | None = None,
    source_module: str = "offline", **extra,
) -> dict:
    """Build the canonical minimum payload for an Offline event."""
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "cache_entry_id": cache_entry_id,
        "expiration_policy_id": expiration_policy_id,
        "workstation_id": workstation_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload

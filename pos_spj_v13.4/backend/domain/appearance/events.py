"""Canonical Appearance domain events — SET-22. Mirrors
backend/domain/feature_flags/events.py's shape. All post-commit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class AppearanceEvents:
    THEME_REGISTERED = "APPEARANCE_THEME_REGISTERED"
    THEME_DEFAULT_CHANGED = "APPEARANCE_THEME_DEFAULT_CHANGED"
    TOKEN_UPDATED = "APPEARANCE_TOKEN_UPDATED"
    DENSITY_PROFILE_REGISTERED = "APPEARANCE_DENSITY_PROFILE_REGISTERED"
    PREFERENCE_UPDATED = "APPEARANCE_PREFERENCE_UPDATED"


ALL_APPEARANCE_EVENTS = frozenset(
    value for key, value in vars(AppearanceEvents).items()
    if not key.startswith("_") and isinstance(value, str)
)


def build_event_payload(
    event_name: str, *, operation_id: str, theme_id: str | None = None, token_id: str | None = None,
    density_profile_id: str | None = None, preference_id: str | None = None, user_id: str | None = None,
    source_module: str = "appearance", **extra,
) -> dict:
    """Build the canonical minimum payload for an Appearance event."""
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "theme_id": theme_id,
        "token_id": token_id,
        "density_profile_id": density_profile_id,
        "preference_id": preference_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload

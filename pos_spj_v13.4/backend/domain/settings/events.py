"""Canonical Settings (Configuration Governance) domain events — SET-2
(§61). Mirrors backend/domain/crm/events.py's shape. All post-commit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class ConfigurationEvents:
    DEFINITION_CREATED = "CONFIGURATION_DEFINITION_CREATED"
    DEFINITION_DEPRECATED = "CONFIGURATION_DEFINITION_DEPRECATED"

    VALUE_CREATED = "CONFIGURATION_VALUE_CREATED"
    CHANGE_SUBMITTED = "CONFIGURATION_CHANGE_SUBMITTED"
    APPROVED = "CONFIGURATION_APPROVED"
    REJECTED = "CONFIGURATION_REJECTED"
    ACTIVATED = "CONFIGURATION_ACTIVATED"
    SCHEDULED = "CONFIGURATION_SCHEDULED"
    EXPIRED = "CONFIGURATION_EXPIRED"
    CANCELLED = "CONFIGURATION_CANCELLED"
    ROLLED_BACK = "CONFIGURATION_ROLLED_BACK"
    CACHE_INVALIDATED = "CONFIGURATION_CACHE_INVALIDATED"

    COMPANY_PROFILE_UPDATED = "COMPANY_PROFILE_UPDATED"

    BRANCH_PROFILE_CREATED = "BRANCH_PROFILE_CREATED"
    BRANCH_PROFILE_UPDATED = "BRANCH_PROFILE_UPDATED"
    BRANCH_PROFILE_ACTIVATED = "BRANCH_PROFILE_ACTIVATED"
    BRANCH_PROFILE_DEACTIVATED = "BRANCH_PROFILE_DEACTIVATED"

    WORKSTATION_REGISTERED = "WORKSTATION_REGISTERED"
    WORKSTATION_ACTIVATED = "WORKSTATION_ACTIVATED"
    WORKSTATION_DEACTIVATED = "WORKSTATION_DEACTIVATED"
    WORKSTATION_ENTERED_MAINTENANCE = "WORKSTATION_ENTERED_MAINTENANCE"
    WORKSTATION_BLOCKED = "WORKSTATION_BLOCKED"
    WORKSTATION_UNBLOCKED = "WORKSTATION_UNBLOCKED"
    WORKSTATION_RETIRED = "WORKSTATION_RETIRED"


ALL_CONFIGURATION_EVENTS = frozenset(
    value for key, value in vars(ConfigurationEvents).items()
    if not key.startswith("_") and isinstance(value, str)
)


def build_event_payload(
    event_name: str, *, operation_id: str, definition_id: str | None = None,
    value_id: str | None = None, user_id: str | None = None,
    branch_id: str | None = None, source_module: str = "settings", **extra,
) -> dict:
    """Build the canonical minimum payload for a Configuration Governance event."""
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "definition_id": definition_id,
        "value_id": value_id,
        "user_id": user_id,
        "branch_id": branch_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload

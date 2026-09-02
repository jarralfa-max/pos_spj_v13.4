"""Canonical Device Management domain events — SET-7 (§61). Mirrors
backend/domain/settings/events.py's shape. All post-commit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class DeviceManagementEvents:
    DEVICE_REGISTERED = "DEVICE_REGISTERED"
    DEVICE_UPDATED = "DEVICE_UPDATED"
    DEVICE_ACTIVATED = "DEVICE_ACTIVATED"
    DEVICE_DEACTIVATED = "DEVICE_DEACTIVATED"
    DEVICE_ENTERED_MAINTENANCE = "DEVICE_ENTERED_MAINTENANCE"
    DEVICE_BLOCKED = "DEVICE_BLOCKED"
    DEVICE_UNBLOCKED = "DEVICE_UNBLOCKED"
    DEVICE_RETIRED = "DEVICE_RETIRED"

    DEVICE_PROFILE_CREATED = "DEVICE_PROFILE_CREATED"
    DEVICE_PROFILE_UPDATED = "DEVICE_PROFILE_UPDATED"

    DEVICE_ASSIGNED = "DEVICE_ASSIGNED"
    DEVICE_UNASSIGNED = "DEVICE_UNASSIGNED"

    PRINT_ROUTE_CREATED = "PRINT_ROUTE_CREATED"
    PRINT_ROUTE_UPDATED = "PRINT_ROUTE_UPDATED"
    PRINT_ROUTE_ACTIVATED = "PRINT_ROUTE_ACTIVATED"
    PRINT_ROUTE_DEACTIVATED = "PRINT_ROUTE_DEACTIVATED"
    PRINTER_FAILOVER_TRIGGERED = "PRINTER_FAILOVER_TRIGGERED"
    PRINTER_TEST_RECORDED = "PRINTER_TEST_RECORDED"

    DEVICE_TEST_RECORDED = "DEVICE_TEST_RECORDED"
    SCALE_STABILITY_CONFIRMED = "SCALE_STABILITY_CONFIRMED"

    CASH_DRAWER_OPENED = "CASH_DRAWER_OPENED"
    CASH_DRAWER_OPEN_DENIED = "CASH_DRAWER_OPEN_DENIED"


ALL_DEVICE_MANAGEMENT_EVENTS = frozenset(
    value for key, value in vars(DeviceManagementEvents).items()
    if not key.startswith("_") and isinstance(value, str)
)


def build_event_payload(
    event_name: str, *, operation_id: str, device_id: str | None = None,
    workstation_id: str | None = None, user_id: str | None = None,
    branch_id: str | None = None, source_module: str = "device_management", **extra,
) -> dict:
    """Build the canonical minimum payload for a Device Management event."""
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "device_id": device_id,
        "workstation_id": workstation_id,
        "user_id": user_id,
        "branch_id": branch_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload

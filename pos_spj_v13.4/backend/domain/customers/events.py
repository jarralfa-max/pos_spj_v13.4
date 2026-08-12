"""Canonical Customer Master domain events (§77) — names + payload builder.

Published post-commit by the application layer via the outbox, same pattern
as backend/domain/suppliers/events.py. Only the Customer Master subset of
§77's event catalog lives here; Leads/Opportunities/Activities/Cases events
land in backend/domain/crm/events.py when CRM-4+ builds those entities.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class CustomerEvents:
    CREATED = "CUSTOMER_CREATED"
    UPDATED = "CUSTOMER_UPDATED"
    ACTIVATED = "CUSTOMER_ACTIVATED"
    DEACTIVATED = "CUSTOMER_DEACTIVATED"
    SUSPENDED = "CUSTOMER_SUSPENDED"
    BLOCKED = "CUSTOMER_BLOCKED"
    CLOSED = "CUSTOMER_CLOSED"
    OWNER_ASSIGNED = "CUSTOMER_OWNER_ASSIGNED"
    TERRITORY_CHANGED = "CUSTOMER_TERRITORY_CHANGED"
    CONTACT_ADDED = "CUSTOMER_CONTACT_ADDED"
    CONTACT_UPDATED = "CUSTOMER_CONTACT_UPDATED"
    CONTACT_REMOVED = "CUSTOMER_CONTACT_REMOVED"
    ADDRESS_ADDED = "CUSTOMER_ADDRESS_ADDED"
    ADDRESS_UPDATED = "CUSTOMER_ADDRESS_UPDATED"
    ADDRESS_REMOVED = "CUSTOMER_ADDRESS_REMOVED"
    TAX_PROFILE_UPDATED = "CUSTOMER_TAX_PROFILE_UPDATED"


ALL_CUSTOMER_EVENTS = frozenset(
    v for k, v in vars(CustomerEvents).items() if not k.startswith("_") and isinstance(v, str)
)


def build_event_payload(event_name: str, *, operation_id: str, customer_id: str,
                        user_id: str | None = None, branch_id: str | None = None,
                        source_module: str = "customers", **extra) -> dict:
    """Build the canonical minimum payload for a Customer Master event."""
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "customer_id": customer_id,
        "user_id": user_id,
        "branch_id": branch_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload

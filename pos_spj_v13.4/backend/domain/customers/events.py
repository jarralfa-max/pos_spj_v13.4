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
    # CRM-13 (§49 Ventas): fired only when Customer.record_sale_activity()
    # actually advances lifecycle_stage, not on every sale (that would just
    # be noise indistinguishable from the sale event itself).
    LIFECYCLE_STAGE_CHANGED = "CUSTOMER_LIFECYCLE_STAGE_CHANGED"
    CONTACT_ADDED = "CUSTOMER_CONTACT_ADDED"
    CONTACT_UPDATED = "CUSTOMER_CONTACT_UPDATED"
    CONTACT_REMOVED = "CUSTOMER_CONTACT_REMOVED"
    ADDRESS_ADDED = "CUSTOMER_ADDRESS_ADDED"
    ADDRESS_UPDATED = "CUSTOMER_ADDRESS_UPDATED"
    ADDRESS_REMOVED = "CUSTOMER_ADDRESS_REMOVED"
    TAX_PROFILE_UPDATED = "CUSTOMER_TAX_PROFILE_UPDATED"

    DUPLICATE_DETECTED = "CUSTOMER_DUPLICATE_DETECTED"
    DUPLICATE_UNDER_REVIEW = "CUSTOMER_DUPLICATE_UNDER_REVIEW"
    DUPLICATE_CONFIRMED = "CUSTOMER_DUPLICATE_CONFIRMED"
    DUPLICATE_DISMISSED = "CUSTOMER_DUPLICATE_DISMISSED"

    MERGE_PROPOSED = "CUSTOMER_MERGE_PROPOSED"
    MERGE_EXECUTED = "CUSTOMER_MERGE_EXECUTED"
    MERGE_REJECTED = "CUSTOMER_MERGE_REJECTED"

    DATA_QUALITY_ISSUE_DETECTED = "CUSTOMER_DATA_QUALITY_ISSUE_DETECTED"
    DATA_QUALITY_ISSUE_ACKNOWLEDGED = "CUSTOMER_DATA_QUALITY_ISSUE_ACKNOWLEDGED"
    DATA_QUALITY_ISSUE_CORRECTED = "CUSTOMER_DATA_QUALITY_ISSUE_CORRECTED"
    DATA_QUALITY_ISSUE_DISMISSED = "CUSTOMER_DATA_QUALITY_ISSUE_DISMISSED"

    IMPORT_BATCH_SUBMITTED = "CUSTOMER_IMPORT_BATCH_SUBMITTED"
    IMPORT_BATCH_APPROVED = "CUSTOMER_IMPORT_BATCH_APPROVED"
    IMPORT_BATCH_COMPLETED = "CUSTOMER_IMPORT_BATCH_COMPLETED"


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

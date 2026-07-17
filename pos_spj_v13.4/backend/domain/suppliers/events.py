"""Canonical supplier domain events (names + payload builder).

Events are published post-commit by the application layer (via the outbox). The
minimum payload carries the identity/actor/branch/timestamp/source needed for
sync and audit. No event is published before the commit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class SupplierEvents:
    CREATED = "SUPPLIER_CREATED"
    UPDATED = "SUPPLIER_UPDATED"
    SUBMITTED_FOR_APPROVAL = "SUPPLIER_SUBMITTED_FOR_APPROVAL"
    APPROVED = "SUPPLIER_APPROVED"
    REJECTED = "SUPPLIER_REJECTED"
    ACTIVATED = "SUPPLIER_ACTIVATED"
    SUSPENDED = "SUPPLIER_SUSPENDED"
    BLOCKED = "SUPPLIER_BLOCKED"
    UNBLOCKED = "SUPPLIER_UNBLOCKED"
    BANK_ACCOUNT_CHANGED = "SUPPLIER_BANK_ACCOUNT_CHANGED"
    BANK_ACCOUNT_VERIFIED = "SUPPLIER_BANK_ACCOUNT_VERIFIED"
    TERMS_UPDATED = "SUPPLIER_TERMS_UPDATED"
    PRODUCT_ASSIGNED = "SUPPLIER_PRODUCT_ASSIGNED"
    EVALUATED = "SUPPLIER_EVALUATED"
    DOCUMENT_EXPIRING = "SUPPLIER_DOCUMENT_EXPIRING"
    RISK_CHANGED = "SUPPLIER_RISK_CHANGED"
    CHANGED = "SUPPLIERS_CHANGED"


ALL_SUPPLIER_EVENTS = frozenset(
    v for k, v in vars(SupplierEvents).items() if not k.startswith("_") and isinstance(v, str)
)


def build_event_payload(event_name: str, *, operation_id: str, supplier_id: str,
                        user_id: str | None = None, branch_id: str | None = None,
                        source_module: str = "suppliers", **extra) -> dict:
    """Build the canonical minimum payload for a supplier event."""
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "supplier_id": supplier_id,
        "user_id": user_id,
        "branch_id": branch_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload

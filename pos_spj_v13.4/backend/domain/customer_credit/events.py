"""Canonical Customer Credit domain events (§77) — names + payload
builder. Mirrors backend/domain/customer_service/events.py. Own namespace
(not folded into CustomerEvents/CRMEvents) — ``customer_credit`` is its own
sub-bounded-context per CRM-1's package layout, with its own schema file
and UnitOfWork.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class CustomerCreditEvents:
    CREDIT_REQUESTED = "CUSTOMER_CREDIT_REQUESTED"
    CREDIT_REVIEWED = "CUSTOMER_CREDIT_REVIEWED"
    CREDIT_APPROVED = "CUSTOMER_CREDIT_APPROVED"
    CREDIT_REJECTED = "CUSTOMER_CREDIT_REJECTED"
    CREDIT_LIMIT_UPDATED = "CUSTOMER_CREDIT_LIMIT_UPDATED"
    CREDIT_LIMIT_OVERRIDDEN = "CUSTOMER_CREDIT_LIMIT_OVERRIDDEN"
    CREDIT_SUSPENDED = "CUSTOMER_CREDIT_SUSPENDED"
    CREDIT_BLOCKED = "CUSTOMER_CREDIT_BLOCKED"
    CREDIT_REOPENED = "CUSTOMER_CREDIT_REOPENED"
    CREDIT_CLOSED = "CUSTOMER_CREDIT_CLOSED"


ALL_CUSTOMER_CREDIT_EVENTS = frozenset(
    v for k, v in vars(CustomerCreditEvents).items()
    if not k.startswith("_") and isinstance(v, str)
)


def build_event_payload(event_name: str, *, operation_id: str, customer_id: str | None = None,
                        profile_id: str | None = None, user_id: str | None = None,
                        branch_id: str | None = None, source_module: str = "customer_credit",
                        **extra) -> dict:
    """Build the canonical minimum payload for a Customer Credit event."""
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "customer_id": customer_id,
        "profile_id": profile_id,
        "user_id": user_id,
        "branch_id": branch_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload

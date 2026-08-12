"""Canonical Customer Service domain events (§77) — names + payload
builder. Mirrors backend/domain/customers/events.py /
backend/domain/crm/events.py. A separate ``CustomerServiceEvents`` class
(not folded into ``CRMEvents``) because this is its own sub-bounded-context
(``customer_service``, per CRM-1's package layout) with its own schema
file and UnitOfWork — same boundary CustomerEvents/CRMEvents already keep
sharp between ``customers`` and ``crm``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class CustomerServiceEvents:
    CASE_CREATED = "CASE_CREATED"
    CASE_UPDATED = "CASE_UPDATED"
    CASE_ASSIGNED = "CASE_ASSIGNED"
    CASE_STARTED = "CASE_STARTED"
    CASE_WAITING_CUSTOMER = "CASE_WAITING_CUSTOMER"
    CASE_WAITING_INTERNAL = "CASE_WAITING_INTERNAL"
    CASE_RESUMED = "CASE_RESUMED"
    CASE_ESCALATED = "CASE_ESCALATED"
    CASE_RESOLVED = "CASE_RESOLVED"
    CASE_CLOSED = "CASE_CLOSED"
    CASE_CANCELLED = "CASE_CANCELLED"
    CASE_REOPENED = "CASE_REOPENED"
    SLA_FIRST_RESPONSE_RECORDED = "SLA_FIRST_RESPONSE_RECORDED"
    SLA_OVERRIDDEN = "SLA_OVERRIDDEN"


ALL_CUSTOMER_SERVICE_EVENTS = frozenset(
    v for k, v in vars(CustomerServiceEvents).items()
    if not k.startswith("_") and isinstance(v, str)
)


def build_event_payload(event_name: str, *, operation_id: str, case_id: str | None = None,
                        user_id: str | None = None, branch_id: str | None = None,
                        source_module: str = "customer_service", **extra) -> dict:
    """Build the canonical minimum payload for a Customer Service event."""
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "case_id": case_id,
        "user_id": user_id,
        "branch_id": branch_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload

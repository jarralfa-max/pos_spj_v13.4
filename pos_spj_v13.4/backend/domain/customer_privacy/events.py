"""Canonical Customer Privacy domain events (§77) — names + payload
builder. Mirrors backend/domain/customer_credit/events.py. Own namespace —
``customer_privacy`` is its own sub-bounded-context per CRM-1's package
layout, with its own schema file and UnitOfWork.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid


class CustomerPrivacyEvents:
    CONSENT_REQUESTED = "CUSTOMER_CONSENT_REQUESTED"
    CONSENT_CAPTURED = "CUSTOMER_CONSENT_CAPTURED"
    CONSENT_CONFIRMED = "CUSTOMER_CONSENT_CONFIRMED"
    CONSENT_WITHDRAWN = "CUSTOMER_CONSENT_WITHDRAWN"
    CONSENT_MARKED_NOT_REQUIRED = "CUSTOMER_CONSENT_MARKED_NOT_REQUIRED"
    COMMUNICATION_PREFERENCE_UPDATED = "CUSTOMER_COMMUNICATION_PREFERENCE_UPDATED"
    PRIVACY_REQUEST_RECEIVED = "CUSTOMER_PRIVACY_REQUEST_RECEIVED"
    PRIVACY_REQUEST_VALIDATING = "CUSTOMER_PRIVACY_REQUEST_VALIDATING"
    PRIVACY_REQUEST_IN_PROGRESS = "CUSTOMER_PRIVACY_REQUEST_IN_PROGRESS"
    PRIVACY_REQUEST_COMPLETED = "CUSTOMER_PRIVACY_REQUEST_COMPLETED"
    PRIVACY_REQUEST_REJECTED = "CUSTOMER_PRIVACY_REQUEST_REJECTED"
    PRIVACY_REQUEST_CANCELLED = "CUSTOMER_PRIVACY_REQUEST_CANCELLED"
    CUSTOMER_ANONYMIZED = "CUSTOMER_ANONYMIZED"


ALL_CUSTOMER_PRIVACY_EVENTS = frozenset(
    v for k, v in vars(CustomerPrivacyEvents).items()
    if not k.startswith("_") and isinstance(v, str)
)


def build_event_payload(event_name: str, *, operation_id: str, customer_id: str | None = None,
                        request_id: str | None = None, consent_id: str | None = None,
                        user_id: str | None = None, branch_id: str | None = None,
                        source_module: str = "customer_privacy", **extra) -> dict:
    """Build the canonical minimum payload for a Customer Privacy event."""
    payload = {
        "event_id": new_uuid(),
        "event_name": event_name,
        "operation_id": operation_id,
        "customer_id": customer_id,
        "request_id": request_id,
        "consent_id": consent_id,
        "user_id": user_id,
        "branch_id": branch_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": source_module,
    }
    payload.update(extra)
    return payload

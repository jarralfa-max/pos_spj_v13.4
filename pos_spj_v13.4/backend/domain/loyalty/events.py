"""Canonical Fidelidad/Loyalty event names and payload contract (master
prompt §62). Mirrors ``backend/domain/sales/events.py``'s `SaleEvents`/
`sale_event_payload()` shape.

This is the TARGET vocabulary for the Program/Account/Membership/Transaction
entities built in LOY-2 — it is NOT wired into the real, running EventBus in
this phase (no use case exists yet that calls these entities from a
persisted, transactional context; that is LOY-4..6's job).

**Important interop decision, not incidental**: 4 of these 15 names —
``POINTS_ISSUED``, ``POINTS_EXPIRED``, ``REWARD_GRANTED`` and
``TRANSACTION_REVERSED`` — are DELIBERATELY the exact same string values as
``backend.shared.events.event_names.EventName.LOYALTY_POINTS_ISSUED`` /
``LOYALTY_POINTS_EXPIRED`` / ``LOYALTY_REWARD_GRANTED`` /
``LOYALTY_TRANSACTION_REVERSED`` — the canonical names Finance's 12 already-
built, already-tested event handlers
(``backend/application/event_handlers/finance/loyalty_*_handler.py``)
listen for (LOY-0 audit finding: nothing in the repo publishes them today).
Reusing the exact literal here means a future phase that wires real
publishing only has to route the string through, never reconcile two
different vocabularies for the same concept. The legacy bus's own
``LOYALTY_POINTS_EARNED``/``LOYALTY_POINTS_REDEEMED`` (different names, same
``core/events/event_bus.py`` still driving `core/services/loyalty_service.py`
in production) are a THIRD, separate vocabulary — deliberately not reused
here; do not conflate the three.
"""
from datetime import datetime, timezone

from backend.shared.ids import new_uuid, validate_uuidv7


class LoyaltyEvents:
    PROGRAM_CREATED = "LOYALTY_PROGRAM_CREATED"
    PROGRAM_ACTIVATED = "LOYALTY_PROGRAM_ACTIVATED"
    MEMBERSHIP_ENROLLED = "LOYALTY_MEMBERSHIP_ENROLLED"
    MEMBERSHIP_SUSPENDED = "LOYALTY_MEMBERSHIP_SUSPENDED"
    POINTS_ISSUED = "LOYALTY_POINTS_ISSUED"
    POINTS_RESERVED = "LOYALTY_POINTS_RESERVED"
    POINTS_REDEEMED = "LOYALTY_POINTS_REDEEMED"
    POINTS_RELEASED = "LOYALTY_POINTS_RELEASED"
    POINTS_EXPIRED = "LOYALTY_POINTS_EXPIRED"
    POINTS_ADJUSTED = "LOYALTY_POINTS_ADJUSTED"
    TRANSACTION_REVERSED = "LOYALTY_TRANSACTION_REVERSED"
    TIER_CHANGED = "LOYALTY_TIER_CHANGED"
    REWARD_GRANTED = "LOYALTY_REWARD_GRANTED"
    CHALLENGE_COMPLETED = "LOYALTY_CHALLENGE_COMPLETED"
    REFERRAL_QUALIFIED = "LOYALTY_REFERRAL_QUALIFIED"
    FRAUD_CASE_OPENED = "LOYALTY_FRAUD_CASE_OPENED"
    FRAUD_CASE_CONFIRMED = "LOYALTY_FRAUD_CASE_CONFIRMED"
    FRAUD_CASE_DISMISSED = "LOYALTY_FRAUD_CASE_DISMISSED"


SYSTEM_ACTOR_ID = "01900000-0000-7000-8000-000000000000"
"""Well-known, fixed UUIDv7-shaped identity for system-triggered (no human
actor) events — e.g. the expiration sweep in LOY-6. Never generated fresh
(that would fabricate a fake identity per event); a single constant, mirrors
`SYSTEM_AUTOMATION_ACTOR` (CRM-26) except REGLA CERO requires every event's
`user_id` to actually be UUIDv7-shaped, so a plain string sentinel like
CRM's won't pass `loyalty_event_payload`'s validation."""

ALL_LOYALTY_EVENTS = frozenset(
    value for name, value in vars(LoyaltyEvents).items()
    if name.isupper() and isinstance(value, str)
)

# Subset that shares its literal string with a real, already-wired Finance
# handler (see module docstring) — kept as a named set so a future wiring
# phase/test can assert it stays a subset of EventName without importing
# backend.shared.events here (domain layer must not depend on it).
FINANCE_ALIGNED_EVENTS = frozenset({
    LoyaltyEvents.POINTS_ISSUED,
    LoyaltyEvents.POINTS_EXPIRED,
    LoyaltyEvents.REWARD_GRANTED,
    LoyaltyEvents.TRANSACTION_REVERSED,
})


def loyalty_event_payload(event_name: str, *, operation_id: str, entity_id: str,
                           branch_id: str, user_id: str, **payload: object) -> dict[str, object]:
    if event_name not in ALL_LOYALTY_EVENTS:
        raise ValueError(f"Unknown canonical Loyalty event: {event_name}")
    for value in (operation_id, entity_id, branch_id, user_id):
        validate_uuidv7(value)
    event_id = new_uuid()
    if event_id in {operation_id, entity_id}:
        raise ValueError("event_id, operation_id and entity_id must be distinct")
    return {
        "event_id": event_id,
        "event_name": event_name,
        "operation_id": operation_id,
        "entity_id": entity_id,
        "branch_id": branch_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_module": "loyalty",
        "payload": payload,
    }

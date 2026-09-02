"""Canonical Sweepstakes event names and payload contract (master prompt
§27-28, §55/§62). Mirrors ``backend/domain/commercial_instruments/events.py``'s
shape.

Unlike Loyalty/Commercial Instruments, `backend/shared/events/event_names.py`
has no RAFFLE/SWEEPSTAKES-aligned members at all (confirmed via grep before
writing this) — there is no existing Finance handler vocabulary to align
with, so this catalog is Sweepstakes-only vocabulary from the start (no
``FINANCE_ALIGNED_EVENTS`` subset)."""
from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid, validate_uuidv7


class SweepstakesEvents:
    CAMPAIGN_CREATED = "SWEEPSTAKES_CAMPAIGN_CREATED"
    CAMPAIGN_APPROVED = "SWEEPSTAKES_CAMPAIGN_APPROVED"
    CAMPAIGN_ACTIVATED = "SWEEPSTAKES_CAMPAIGN_ACTIVATED"
    CAMPAIGN_CLOSED = "SWEEPSTAKES_CAMPAIGN_CLOSED"
    CAMPAIGN_CANCELLED = "SWEEPSTAKES_CAMPAIGN_CANCELLED"

    ENTRY_GRANTED = "SWEEPSTAKES_ENTRY_GRANTED"
    TICKET_ISSUED = "SWEEPSTAKES_TICKET_ISSUED"
    TICKET_PRINTED = "SWEEPSTAKES_TICKET_PRINTED"
    TICKET_VOIDED = "SWEEPSTAKES_TICKET_VOIDED"

    DRAW_SCHEDULED = "SWEEPSTAKES_DRAW_SCHEDULED"
    DRAW_COMPLETED = "SWEEPSTAKES_DRAW_COMPLETED"
    DRAW_CANCELLED = "SWEEPSTAKES_DRAW_CANCELLED"

    WINNER_SELECTED = "SWEEPSTAKES_WINNER_SELECTED"
    WINNER_VALIDATED = "SWEEPSTAKES_WINNER_VALIDATED"
    WINNER_DISQUALIFIED = "SWEEPSTAKES_WINNER_DISQUALIFIED"
    PRIZE_DELIVERED = "SWEEPSTAKES_PRIZE_DELIVERED"


ALL_SWEEPSTAKES_EVENTS = frozenset(
    value for name, value in vars(SweepstakesEvents).items()
    if name.isupper() and isinstance(value, str)
)


def sweepstakes_event_payload(
    event_name: str, *, operation_id: str, entity_id: str, branch_id: str, user_id: str,
    **payload: object,
) -> dict[str, object]:
    if event_name not in ALL_SWEEPSTAKES_EVENTS:
        raise ValueError(f"Unknown canonical Sweepstakes event: {event_name}")
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
        "source_module": "sweepstakes",
        "payload": payload,
    }

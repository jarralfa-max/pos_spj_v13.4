"""Canonical Commercial Instruments event names and payload contract (master
prompt §55/§62). Mirrors ``backend/domain/loyalty/events.py``'s shape.

All 4 of these are DELIBERATELY the exact same string values as
``backend.shared.events.event_names.EventName.COUPON_ISSUED/REDEEMED/
EXPIRED/CANCELLED`` — the canonical names Finance's already-built,
already-tested ``coupon_*_handler.py`` handlers listen for (same LOY-0
"highest value" finding already applied to Loyalty's own event catalog in
LOY-2). Same caveat as LOY-2: no dispatcher wires ``commercial_instruments_
outbox`` to those handlers yet — only the vocabulary is forward-compatible.
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.shared.ids import new_uuid, validate_uuidv7


class CommercialInstrumentEvents:
    COUPON_ISSUED = "COUPON_ISSUED"
    COUPON_RESERVED = "COUPON_RESERVED"
    COUPON_REDEEMED = "COUPON_REDEEMED"
    COUPON_RELEASED = "COUPON_RELEASED"
    COUPON_EXPIRED = "COUPON_EXPIRED"
    COUPON_CANCELLED = "COUPON_CANCELLED"

    VOUCHER_ISSUED = "VOUCHER_ISSUED"
    VOUCHER_RESERVED = "VOUCHER_RESERVED"
    VOUCHER_REDEEMED = "VOUCHER_REDEEMED"
    VOUCHER_RELEASED = "VOUCHER_RELEASED"
    VOUCHER_RELOADED = "VOUCHER_RELOADED"
    VOUCHER_EXPIRED = "VOUCHER_EXPIRED"
    VOUCHER_CANCELLED = "VOUCHER_CANCELLED"
    VOUCHER_REVERSED = "VOUCHER_REVERSED"


ALL_COMMERCIAL_INSTRUMENT_EVENTS = frozenset(
    value for name, value in vars(CommercialInstrumentEvents).items()
    if name.isupper() and isinstance(value, str)
)

# Subset that shares its literal string with a real, already-wired Finance
# handler (`backend/shared/events/event_names.py::EventName`) — provisional
# events (RESERVED/RELEASED) have no Finance handler (reservation is never
# recognized financially until confirmed/redeemed), and EventName has no
# VOUCHER_RELOADED/VOUCHER_REVERSED member either (confirmed via LOY-0's own
# audit) — those two stay Commercial-Instruments-only vocabulary for now.
FINANCE_ALIGNED_EVENTS = frozenset({
    CommercialInstrumentEvents.COUPON_ISSUED,
    CommercialInstrumentEvents.COUPON_REDEEMED,
    CommercialInstrumentEvents.COUPON_EXPIRED,
    CommercialInstrumentEvents.COUPON_CANCELLED,
    CommercialInstrumentEvents.VOUCHER_ISSUED,
    CommercialInstrumentEvents.VOUCHER_REDEEMED,
    CommercialInstrumentEvents.VOUCHER_EXPIRED,
    CommercialInstrumentEvents.VOUCHER_CANCELLED,
})


def commercial_instrument_event_payload(
    event_name: str, *, operation_id: str, entity_id: str, branch_id: str, user_id: str,
    **payload: object,
) -> dict[str, object]:
    if event_name not in ALL_COMMERCIAL_INSTRUMENT_EVENTS:
        raise ValueError(f"Unknown canonical Commercial Instrument event: {event_name}")
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
        "source_module": "commercial_instruments",
        "payload": payload,
    }

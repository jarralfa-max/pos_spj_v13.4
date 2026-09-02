"""Post-commit dispatcher for `orders_delivery_outbox` (master prompt §57-58,
ORD-24 — every prior phase's own comment said "no dispatcher exists yet,
ORD-24 builds it"). Mirrors
`backend/application/procurement/integrations/procurement_outbox_dispatcher.py`'s
exact shape: read PENDING rows, publish each onto the real `core.events.
event_bus.EventBus`, mark DONE on success, retry-with-backoff (eventually
DEAD_LETTER) on failure.

The events published here (`OrderEvents`/`DeliveryEvents`, built ORD-2/15)
have had ZERO real subscribers this whole pipeline — every phase's own
docstring says so explicitly. `EventBus.publish(..., strict=False)` logs and
returns when nobody is listening rather than raising, so wiring this
dispatcher is safe today even though nothing consumes these events yet; a
future phase adds handlers without touching this module.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from backend.infrastructure.db.repositories.orders_delivery.outbox_repository import (
    OrdersDeliveryOutboxRepository,
)

logger = logging.getLogger("spj.orders_delivery.outbox_dispatcher")

_REQUIRED_PAYLOAD_FIELDS = ("event_id", "event_name", "operation_id", "entity_id")


def dispatch_orders_delivery_outbox(connection, bus, *, limit: int = 100,
                                     max_attempts: int = 5) -> dict:
    """Publishes pending `orders_delivery_outbox` rows. Returns a small
    summary dict (`pending`/`dispatched`/`failed`) — the same shape
    `dispatch_procurement_outbox` returns, for a consistent call-site
    convention across bounded contexts."""
    outbox = OrdersDeliveryOutboxRepository(connection)
    pending = outbox.list_pending(limit=limit)
    dispatched = failed = 0
    for row in pending:
        try:
            payload = json.loads(row["payload_json"])
            if not isinstance(payload, dict):
                raise ValueError("outbox payload must be a JSON object")
            _validate_payload(row, payload)
            _publish(bus, row["event_type"], payload)
            outbox.mark_processed(row["id"])
            dispatched += 1
        except Exception as exc:  # noqa: BLE001 - keep the row PENDING/DEAD_LETTER for retry
            failed += 1
            attempts = int(row.get("retries") or 0) + 1
            delay_seconds = min(300, 2 ** min(attempts, 8))
            next_retry_at = (datetime.now(timezone.utc)
                              + timedelta(seconds=delay_seconds)).isoformat(timespec="seconds")
            outbox.mark_failed(row["id"], error=str(exc), next_retry_at=next_retry_at,
                                max_attempts=max_attempts)
            logger.error("orders_delivery outbox dispatch failed id=%s event=%s: %s",
                         row.get("id"), row.get("event_type"), exc)
    if dispatched or failed:
        # Repositories never commit (see base.py's own docstring) — this
        # function IS the transaction boundary for outbox bookkeeping,
        # deliberately separate from whichever OrdersDeliveryUnitOfWork
        # originally enqueued the rows.
        connection.commit()
    return {"pending": len(pending), "dispatched": dispatched, "failed": failed}


def _publish(bus, event_type: str, payload: dict) -> None:
    publish = getattr(bus, "publish", None)
    if publish is None:
        raise RuntimeError("El bus no expone publish()")
    publish(event_type, payload, async_=False)


def _validate_payload(row: dict, payload: dict) -> None:
    """Fail a malformed row into retry/dead-letter instead of publishing a
    payload that doesn't match the row it came from."""
    missing = [key for key in _REQUIRED_PAYLOAD_FIELDS if not payload.get(key)]
    if missing:
        raise ValueError(f"outbox payload missing required fields: {', '.join(missing)}")
    if payload["event_id"] != row["event_id"]:
        raise ValueError("outbox event_id does not match payload")
    if payload["event_name"] != row["event_type"]:
        raise ValueError("outbox event_name does not match payload")
    if payload["operation_id"] != row["operation_id"]:
        raise ValueError("outbox operation_id does not match payload")

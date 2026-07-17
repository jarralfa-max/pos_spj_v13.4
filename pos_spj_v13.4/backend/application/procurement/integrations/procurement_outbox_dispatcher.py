"""Post-commit dispatcher for the procurement transactional outbox.

Procurement use cases enqueue events in ``procurement_outbox`` inside the same
transaction as the state change. This dispatcher publishes the pending rows onto
the EventBus AFTER commit and marks them dispatched, so a crash between commit
and publish never loses an event (it is retried) and never double-applies it
(downstream handlers are idempotent by event_id).
"""

from __future__ import annotations

import json
import logging

from backend.infrastructure.db.repositories.procurement.support_repositories import (
    ProcurementOutboxRepository,
)

logger = logging.getLogger("spj.procurement.outbox_dispatcher")


def dispatch_procurement_outbox(connection, bus, *, limit: int = 100) -> dict:
    """Publish pending procurement outbox events. Returns a small summary dict."""
    outbox = ProcurementOutboxRepository(connection)
    pending = outbox.list_pending(limit=limit)
    dispatched = 0
    failed = 0
    for row in pending:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            payload = {}
        try:
            _publish(bus, row["event_name"], payload)
            outbox.mark_dispatched(row["id"])
            dispatched += 1
        except Exception as exc:  # keep row PENDING for retry
            failed += 1
            logger.error("procurement outbox dispatch failed id=%s event=%s: %s",
                         row.get("id"), row.get("event_name"), exc)
    if dispatched or failed:
        connection.commit()
    return {"pending": len(pending), "dispatched": dispatched, "failed": failed}


def _publish(bus, event_name: str, payload: dict) -> None:
    publish = getattr(bus, "publish", None)
    if publish is None:
        raise RuntimeError("El bus no expone publish()")
    try:
        publish(event_name, payload, async_=False)
    except TypeError:
        publish(event_name, payload)

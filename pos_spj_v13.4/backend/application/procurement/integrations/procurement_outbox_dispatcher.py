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
from datetime import datetime, timedelta, timezone

from backend.infrastructure.db.repositories.procurement.support_repositories import (
    ProcurementOutboxRepository,
)

logger = logging.getLogger("spj.procurement.outbox_dispatcher")


def dispatch_procurement_outbox(connection, bus, *, limit: int = 100,
                                max_attempts: int = 5) -> dict:
    """Publish pending procurement outbox events. Returns a small summary dict."""
    outbox = ProcurementOutboxRepository(connection)
    pending = outbox.list_pending(limit=limit)
    dispatched = 0
    failed = 0
    for row in pending:
        try:
            payload = json.loads(row["payload_json"])
            if not isinstance(payload, dict):
                raise ValueError("outbox payload must be a JSON object")
            _validate_payload(row, payload)
            _publish(bus, row["event_name"], payload)
            outbox.mark_dispatched(row["id"])
            dispatched += 1
        except Exception as exc:  # keep row PENDING for retry
            failed += 1
            attempts = int(row.get("attempt_count") or 0) + 1
            delay_seconds = min(300, 2 ** min(attempts, 8))
            next_attempt = (datetime.now(timezone.utc) + timedelta(
                seconds=delay_seconds)).isoformat(timespec="seconds")
            outbox.mark_failed(row["id"], str(exc), max_attempts=max_attempts,
                               next_attempt_at=next_attempt)
            logger.error("procurement outbox dispatch failed id=%s event=%s: %s",
                         row.get("id"), row.get("event_name"), exc)
    if dispatched or failed:
        connection.commit()
    return {"pending": len(pending), "dispatched": dispatched, "failed": failed}


def _publish(bus, event_name: str, payload: dict) -> None:
    publish = getattr(bus, "publish", None)
    if publish is None:
        raise RuntimeError("El bus no expone publish()")
    publish(event_name, payload, async_=False)


def _validate_payload(row: dict, payload: dict) -> None:
    """Fail malformed rows into retry/dead-letter instead of publishing them."""
    required = ("event_id", "event_name", "operation_id", "schema_version",
                "correlation_id")
    missing = [key for key in required if payload.get(key) in (None, "")]
    if missing:
        raise ValueError(f"outbox payload missing required fields: {', '.join(missing)}")
    if payload["event_id"] != row["event_id"]:
        raise ValueError("outbox event_id does not match payload")
    if payload["event_name"] != row["event_name"]:
        raise ValueError("outbox event_name does not match payload")
    if payload["operation_id"] != row["operation_id"]:
        raise ValueError("outbox operation_id does not match payload")

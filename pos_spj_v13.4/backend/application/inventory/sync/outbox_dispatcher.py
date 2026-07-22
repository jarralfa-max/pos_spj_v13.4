"""InventoryOutboxDispatcher — offline-first relay of the inventory outbox (§57).

Two steps, both idempotent:

- ``register_pending``: give every un-tracked outbox event a per-node monotonic
  sequence and a PENDING dispatch row. This is the local ledger of what still
  needs to leave this node — it survives being offline.
- ``dispatch_due``: for each due PENDING dispatch (backoff elapsed), in sequence
  order, hand the payload to the transport. On success mark DISPATCHED; on
  failure apply exponential backoff (``RetryPolicy``) and, past the cap,
  dead-letter. Afterward advance the sync cursor to the last contiguously-synced
  sequence, so ordering is preserved across reconnects.

Everything runs inside the InventoryUnitOfWork, so dispatch bookkeeping commits
atomically. The dispatcher never mutates stock — it only moves already-committed
events out.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from backend.domain.inventory.services.retry_policy import RetryPolicy
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso_plus(now_iso: str, seconds: int) -> str:
    base = datetime.fromisoformat(now_iso)
    return (base + timedelta(seconds=seconds)).isoformat(timespec="seconds")


class InventoryOutboxDispatcher:
    def __init__(self, connection, *, node_id: str, transport,
                 retry_policy: RetryPolicy | None = None, clock=_now_iso) -> None:
        self._conn = connection
        self._node = node_id
        self._transport = transport
        self._retry = retry_policy or RetryPolicy()
        self._clock = clock

    def register_pending(self, *, limit: int = 1000) -> int:
        created = 0
        with InventoryUnitOfWork(self._conn) as uow:
            for row in uow.outbox.list_pending(limit=limit):
                if uow.sync_dispatch.exists_for_event(row["event_id"]):
                    continue
                sequence = uow.sync_dispatch.next_sequence(self._node)
                uow.sync_dispatch.create(
                    event_id=row["event_id"], operation_id=row["operation_id"],
                    node_id=self._node, sequence=sequence,
                    max_attempts=self._retry.max_attempts)
                created += 1
        return created

    def dispatch_due(self, *, now: str | None = None, limit: int = 100) -> dict:
        now = now or self._clock()
        stats = {"dispatched": 0, "retried": 0, "dead_letter": 0}
        with InventoryUnitOfWork(self._conn) as uow:
            for row in uow.sync_dispatch.list_due(self._node, now=now, limit=limit):
                attempts = row["attempts"] + 1
                outbox = uow.outbox.get_by_event_id(row["event_id"])
                payload = self._payload(row, outbox)
                try:
                    self._transport.send(payload)
                except Exception as exc:  # noqa: BLE001 — any transport failure is retryable
                    if self._retry.should_retry(attempts):
                        uow.sync_dispatch.schedule_retry(
                            row["id"], attempts=attempts,
                            next_attempt_at=_iso_plus(now, self._retry.next_delay_seconds(attempts)),
                            last_error=str(exc))
                        stats["retried"] += 1
                    else:
                        uow.sync_dispatch.dead_letter(
                            row["id"], attempts=attempts, last_error=str(exc))
                        stats["dead_letter"] += 1
                    continue
                uow.sync_dispatch.mark_dispatched(row["id"], attempts=attempts)
                if outbox is not None:
                    uow.outbox.mark_dispatched(outbox["id"])
                stats["dispatched"] += 1
            uow.sync_cursor.advance(
                self._node, uow.sync_dispatch.synced_high_water(self._node))
        return stats

    @staticmethod
    def _payload(dispatch_row: dict, outbox: dict | None) -> dict:
        if outbox and outbox.get("payload_json"):
            return json.loads(outbox["payload_json"])
        return {"event_id": dispatch_row["event_id"],
                "operation_id": dispatch_row["operation_id"]}

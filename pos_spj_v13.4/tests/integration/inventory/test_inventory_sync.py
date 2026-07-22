"""INV-22 — offline-first: dispatch sequence/retry/dead-letter, cursor, ingestor."""

import json
from datetime import datetime, timedelta, timezone

import sqlite3

import pytest

from backend.application.inventory.sync import (
    InMemoryTransport,
    InventoryEventIngestor,
    InventoryOutboxDispatcher,
    SyncTransportError,
)
from backend.domain.inventory.services.retry_policy import RetryPolicy
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

NODE = "terminal-1"
T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _iso(dt):
    return dt.isoformat(timespec="seconds")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _enqueue(conn, n):
    with InventoryUnitOfWork(conn) as uow:
        for i in range(n):
            uow.outbox.enqueue(event_id=f"ev-{i}", event_name="INVENTORY_MOVEMENT_POSTED",
                               payload_json=json.dumps({"event_id": f"ev-{i}", "n": i}),
                               operation_id=f"op-{i}")


class _FailN:
    """Fails the first ``n`` sends, then succeeds."""
    def __init__(self, n):
        self.n = n
        self.sent = []

    def send(self, event):
        if len(self.sent) < self.n:
            self.sent.append(None)
            raise SyncTransportError("network down")
        self.sent.append(event)


class TestDispatch:
    def test_register_assigns_monotonic_sequence(self, conn):
        _enqueue(conn, 3)
        created = InventoryOutboxDispatcher(
            conn, node_id=NODE, transport=InMemoryTransport()).register_pending()
        assert created == 3
        with InventoryUnitOfWork(conn) as uow:
            seqs = [r["sequence"] for r in uow.sync_dispatch.list_by_status(NODE, "PENDING")]
        assert seqs == [1, 2, 3]
        # re-register is idempotent
        again = InventoryOutboxDispatcher(
            conn, node_id=NODE, transport=InMemoryTransport()).register_pending()
        assert again == 0

    def test_happy_path_dispatches_and_advances_cursor(self, conn):
        _enqueue(conn, 3)
        transport = InMemoryTransport()
        disp = InventoryOutboxDispatcher(conn, node_id=NODE, transport=transport)
        disp.register_pending()
        stats = disp.dispatch_due(now=_iso(T0))
        assert stats["dispatched"] == 3
        assert len(transport.sent) == 3
        with InventoryUnitOfWork(conn) as uow:
            assert uow.sync_cursor.get(NODE)["last_sequence"] == 3
            assert uow.outbox.list_pending() == []  # all marked dispatched

    def test_failure_retries_with_backoff_and_blocks_cursor(self, conn):
        _enqueue(conn, 1)
        disp = InventoryOutboxDispatcher(conn, node_id=NODE, transport=_FailN(99),
                                         retry_policy=RetryPolicy(base_seconds=2, max_attempts=5))
        disp.register_pending()
        stats = disp.dispatch_due(now=_iso(T0))
        assert stats["retried"] == 1
        with InventoryUnitOfWork(conn) as uow:
            row = uow.sync_dispatch.list_by_status(NODE, "PENDING")[0]
            assert row["attempts"] == 1
            assert row["next_attempt_at"] == _iso(T0 + timedelta(seconds=2))
            # cursor blocked: nothing contiguously synced
            assert uow.sync_cursor.get(NODE)["last_sequence"] == 0

    def test_not_due_until_backoff_elapses(self, conn):
        _enqueue(conn, 1)
        disp = InventoryOutboxDispatcher(conn, node_id=NODE, transport=_FailN(1),
                                         retry_policy=RetryPolicy(base_seconds=2))
        disp.register_pending()
        disp.dispatch_due(now=_iso(T0))                     # fail → retry at T0+2
        s_early = disp.dispatch_due(now=_iso(T0 + timedelta(seconds=1)))  # not due yet
        assert s_early == {"dispatched": 0, "retried": 0, "dead_letter": 0}
        s_late = disp.dispatch_due(now=_iso(T0 + timedelta(seconds=2)))   # now due → ok
        assert s_late["dispatched"] == 1
        with InventoryUnitOfWork(conn) as uow:
            assert uow.sync_cursor.get(NODE)["last_sequence"] == 1

    def test_dead_letter_after_max_attempts(self, conn):
        _enqueue(conn, 1)
        disp = InventoryOutboxDispatcher(conn, node_id=NODE, transport=_FailN(99),
                                         retry_policy=RetryPolicy(base_seconds=1, max_attempts=2))
        disp.register_pending()
        disp.dispatch_due(now=_iso(T0))                              # attempt 1 → retry
        stats = disp.dispatch_due(now=_iso(T0 + timedelta(seconds=1)))  # attempt 2 → dead
        assert stats["dead_letter"] == 1
        with InventoryUnitOfWork(conn) as uow:
            dead = uow.sync_dispatch.list_by_status(NODE, "DEAD_LETTER")
            assert len(dead) == 1 and dead[0]["attempts"] == 2
            # dead-lettered clears the ordered stream: cursor moves past it
            assert uow.sync_cursor.get(NODE)["last_sequence"] == 1

    def test_ordering_preserved_when_earlier_event_stuck(self, conn):
        # seq1 permanently failing, seq2 ok → cursor must NOT pass seq1.
        with InventoryUnitOfWork(conn) as uow:
            uow.outbox.enqueue(event_id="ev-1", event_name="E",
                               payload_json=json.dumps({"event_id": "ev-1"}),
                               operation_id="op-1")
            uow.outbox.enqueue(event_id="ev-2", event_name="E",
                               payload_json=json.dumps({"event_id": "ev-2"}),
                               operation_id="op-2")

        class FailEv1:
            def send(self, event):
                if event.get("event_id") == "ev-1":
                    raise SyncTransportError("ev-1 stuck")

        disp = InventoryOutboxDispatcher(conn, node_id=NODE, transport=FailEv1(),
                                         retry_policy=RetryPolicy(max_attempts=5))
        disp.register_pending()
        stats = disp.dispatch_due(now=_iso(T0))
        assert stats == {"dispatched": 1, "retried": 1, "dead_letter": 0}
        with InventoryUnitOfWork(conn) as uow:
            # ev-2 dispatched but ev-1 still pending below it → cursor blocked at 0
            assert uow.sync_cursor.get(NODE)["last_sequence"] == 0


class TestIngestor:
    def test_applies_once_and_skips_duplicate(self, conn):
        applied = []
        ing = InventoryEventIngestor(conn)
        ev = {"event_id": "e1", "event_name": "X", "operation_id": "o1"}
        assert ing.ingest(ev, lambda e, uow: applied.append(e["event_id"])) is True
        assert ing.ingest(ev, lambda e, uow: applied.append(e["event_id"])) is False
        assert applied == ["e1"]  # effect ran exactly once

    def test_missing_event_id_rejected(self, conn):
        with pytest.raises(ValueError):
            InventoryEventIngestor(conn).ingest({"event_name": "X"})

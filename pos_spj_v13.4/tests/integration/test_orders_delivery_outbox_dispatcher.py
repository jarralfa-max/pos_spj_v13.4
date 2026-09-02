"""ORD-24 — dispatch_orders_delivery_outbox: publishes PENDING
`orders_delivery_outbox` rows onto a bus, marks DONE on success, retries
with backoff (eventually DEAD_LETTER) on failure. Every prior ORD phase's
own comment said "no dispatcher exists yet, ORD-24 builds it" — this closes
that."""

from __future__ import annotations

import json
import sqlite3

import pytest

from backend.application.orders_delivery.integrations.orders_delivery_outbox_dispatcher import (
    dispatch_orders_delivery_outbox,
)
from backend.domain.orders_delivery.events import OrderEvents, order_event_payload
from backend.infrastructure.db.repositories.orders_delivery.outbox_repository import (
    OrdersDeliveryOutboxRepository,
)
from backend.infrastructure.db.schema.orders_delivery_schema import create_orders_delivery_schema
from backend.shared.ids import new_uuid


class _FakeBus:
    def __init__(self, *, fail_events: set[str] | None = None) -> None:
        self.published: list[tuple[str, dict]] = []
        self._fail_events = fail_events or set()

    def publish(self, event_type: str, payload: dict, async_: bool = False) -> None:
        if event_type in self._fail_events:
            raise RuntimeError("bus unavailable")
        self.published.append((event_type, payload))


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    create_orders_delivery_schema(connection)
    yield connection
    connection.close()


def _enqueue_order_created(conn, *, order_id: str | None = None,
                            operation_id: str | None = None) -> str:
    order_id = order_id or new_uuid()
    operation_id = operation_id or new_uuid()
    branch_id, user_id = new_uuid(), new_uuid()
    payload = order_event_payload(
        OrderEvents.CREATED, operation_id=operation_id, entity_id=order_id,
        branch_id=branch_id, user_id=user_id, channel="POS")
    OrdersDeliveryOutboxRepository(conn).enqueue(
        event_id=payload["event_id"], aggregate_type="CustomerOrder", aggregate_id=order_id,
        event_type=OrderEvents.CREATED, payload_json=json.dumps(payload), operation_id=operation_id)
    conn.commit()
    return order_id


class TestDispatchSuccess:
    def test_publishes_and_marks_done(self, conn):
        order_id = _enqueue_order_created(conn)
        bus = _FakeBus()

        stats = dispatch_orders_delivery_outbox(conn, bus)

        assert stats == {"pending": 1, "dispatched": 1, "failed": 0}
        assert len(bus.published) == 1
        event_type, payload = bus.published[0]
        assert event_type == OrderEvents.CREATED
        assert payload["entity_id"] == order_id
        row = conn.execute(
            "SELECT status, processed_at FROM orders_delivery_outbox WHERE aggregate_id=?",
            (order_id,)).fetchone()
        assert row[0] == "DONE"
        assert row[1] is not None

    def test_dispatched_rows_are_not_republished(self, conn):
        _enqueue_order_created(conn)
        bus = _FakeBus()
        dispatch_orders_delivery_outbox(conn, bus)

        stats = dispatch_orders_delivery_outbox(conn, bus)

        assert stats == {"pending": 0, "dispatched": 0, "failed": 0}
        assert len(bus.published) == 1

    def test_no_handlers_registered_is_not_a_failure(self, conn):
        """`EventBus.publish(strict=False)` just logs when nobody is
        listening — every ORD event has zero real subscribers so far, and
        that must still count as a successful dispatch, not a retry."""
        order_id = _enqueue_order_created(conn)

        class _RealShapedBus:
            def publish(self, event_type, payload, async_=False):
                return None  # no handlers registered => no-op, no raise

        stats = dispatch_orders_delivery_outbox(conn, _RealShapedBus())

        assert stats["dispatched"] == 1
        row = conn.execute(
            "SELECT status FROM orders_delivery_outbox WHERE aggregate_id=?",
            (order_id,)).fetchone()
        assert row[0] == "DONE"


class TestRealEventBus:
    def test_publishes_onto_the_real_process_wide_event_bus(self, conn):
        """`EventBus` is a process-wide singleton (`core/events/event_bus.py`)
        — this proves the dispatcher genuinely calls its real `publish()`,
        not just something shaped like it. The subscribed handler is
        removed in `finally` so this test never leaks state into others."""
        from core.events.event_bus import EventBus

        bus = EventBus()
        received: list[dict] = []

        def _handler(payload: dict) -> None:
            received.append(payload)

        bus.subscribe(OrderEvents.CREATED, _handler, label="test_ord24_real_bus")
        try:
            order_id = _enqueue_order_created(conn)
            stats = dispatch_orders_delivery_outbox(conn, bus)
        finally:
            bus.unsubscribe(OrderEvents.CREATED, _handler)

        assert stats["dispatched"] == 1
        assert len(received) == 1
        assert received[0]["entity_id"] == order_id


class TestDispatchFailureRetry:
    def test_bus_failure_keeps_row_pending_with_future_retry(self, conn):
        _enqueue_order_created(conn)
        bus = _FakeBus(fail_events={OrderEvents.CREATED})

        stats = dispatch_orders_delivery_outbox(conn, bus)

        assert stats == {"pending": 1, "dispatched": 0, "failed": 1}
        row = conn.execute(
            "SELECT status, retries, next_retry_at FROM orders_delivery_outbox").fetchone()
        assert row[0] == "PENDING"
        assert row[1] == 1
        assert row[2] is not None

    def test_pending_row_with_future_retry_is_not_redispatched_immediately(self, conn):
        _enqueue_order_created(conn)
        dispatch_orders_delivery_outbox(conn, _FakeBus(fail_events={OrderEvents.CREATED}))

        stats = dispatch_orders_delivery_outbox(conn, _FakeBus())

        assert stats == {"pending": 0, "dispatched": 0, "failed": 0}

    def test_exhausting_max_attempts_moves_to_dead_letter(self, conn):
        _enqueue_order_created(conn)
        bus = _FakeBus(fail_events={OrderEvents.CREATED})

        for _ in range(3):
            conn.execute("UPDATE orders_delivery_outbox SET next_retry_at=NULL")
            dispatch_orders_delivery_outbox(conn, bus, max_attempts=3)

        row = conn.execute("SELECT status, retries FROM orders_delivery_outbox").fetchone()
        assert row == ("DEAD_LETTER", 3)

    def test_malformed_payload_is_retried_not_crashed(self, conn):
        order_id = new_uuid()
        OrdersDeliveryOutboxRepository(conn).enqueue(
            event_id=new_uuid(), aggregate_type="CustomerOrder", aggregate_id=order_id,
            event_type=OrderEvents.CREATED, payload_json="not json", operation_id=new_uuid())
        conn.commit()
        bus = _FakeBus()

        stats = dispatch_orders_delivery_outbox(conn, bus)

        assert stats == {"pending": 1, "dispatched": 0, "failed": 1}
        assert bus.published == []
        row = conn.execute("SELECT status FROM orders_delivery_outbox").fetchone()
        assert row[0] == "PENDING"

"""ORD-3 — the born-clean UUIDv7 schema for the Pedidos/Delivery bounded
context (migration 226). Verifies the DDL is idempotent, creates the
expected tables/indexes, and enforces the structural idempotency
constraints (§58) as real SQL, not just an application-layer promise."""

from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.schema.orders_delivery_schema import (
    ORDERS_DELIVERY_TABLES,
    create_orders_delivery_schema,
    drop_orders_delivery_schema,
)


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    create_orders_delivery_schema(connection)
    yield connection
    connection.close()


def test_creates_all_expected_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {row[0] for row in rows}
    for table in ORDERS_DELIVERY_TABLES:
        assert table in names


def test_schema_creation_is_idempotent(conn):
    create_orders_delivery_schema(conn)  # must not raise on re-run


def test_customer_orders_operation_id_is_unique(conn):
    conn.execute(
        "INSERT INTO customer_orders (id, branch_id, channel, order_type, "
        "fulfillment_type, operation_id, created_at, updated_at) "
        "VALUES ('o1','b1','POS','STANDARD','COUNTER','op-1','t','t')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO customer_orders (id, branch_id, channel, order_type, "
            "fulfillment_type, operation_id, created_at, updated_at) "
            "VALUES ('o2','b1','POS','STANDARD','COUNTER','op-1','t','t')")


def test_customer_orders_channel_external_reference_dedup(conn):
    conn.execute(
        "INSERT INTO customer_orders (id, branch_id, channel, order_type, "
        "fulfillment_type, operation_id, external_order_reference, created_at, updated_at) "
        "VALUES ('o1','b1','WHATSAPP','STANDARD','HOME_DELIVERY','op-1','wa-msg-1','t','t')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO customer_orders (id, branch_id, channel, order_type, "
            "fulfillment_type, operation_id, external_order_reference, created_at, updated_at) "
            "VALUES ('o2','b1','WHATSAPP','STANDARD','HOME_DELIVERY','op-2','wa-msg-1','t','t')")


def test_orders_delivery_outbox_operation_id_is_unique(conn):
    conn.execute(
        "INSERT INTO orders_delivery_outbox (id, event_id, aggregate_type, aggregate_id, "
        "event_type, payload_json, operation_id, created_at) "
        "VALUES ('e1','ev-1','CustomerOrder','o1','ORDER_CREATED','{}','op-1','t')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO orders_delivery_outbox (id, event_id, aggregate_type, aggregate_id, "
            "event_type, payload_json, operation_id, created_at) "
            "VALUES ('e2','ev-2','CustomerOrder','o1','ORDER_CREATED','{}','op-1','t')")


def test_drop_schema_removes_all_tables(conn):
    dropped = drop_orders_delivery_schema(conn)
    assert set(dropped) == set(ORDERS_DELIVERY_TABLES)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {row[0] for row in rows}
    for table in ORDERS_DELIVERY_TABLES:
        assert table not in names


def test_no_collision_with_legacy_delivery_tables(conn):
    """§1/§3 of orders_delivery_legacy_inventory.md: the new canonical names
    must never collide with the legacy delivery_orders/delivery_items/etc.
    tables this migration deliberately does not touch."""
    legacy_names = {
        "delivery_orders", "delivery_items", "delivery_order_history",
        "drivers", "delivery_outbox_events", "pedidos_whatsapp",
        "pedidos_whatsapp_items",
    }
    assert legacy_names.isdisjoint(ORDERS_DELIVERY_TABLES)

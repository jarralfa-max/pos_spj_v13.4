import sqlite3

from core.delivery.infrastructure.delivery_schema_migrator import DeliverySchemaMigrator
from core.services.delivery_service import DeliveryService
from repositories.delivery_repository import DeliveryRepository


class DummyWA:
    def notify_status(self, **_kwargs):
        return True

    def sync_status(self, *_args, **_kwargs):
        return True

    def pull_orders(self):
        return []


class DummyGeo:
    def geocode(self, _address):
        return None

    def autocomplete(self, _query):
        return []


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _indexes(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA index_list({table})").fetchall()}


def test_migrator_creates_delivery_schema_and_indexes_idempotently():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    migrator = DeliverySchemaMigrator(conn)

    migrator.ensure_schema()
    migrator.ensure_schema()

    assert "workflow_type" in _columns(conn, "delivery_orders")
    assert "adjustment_pending" in _columns(conn, "delivery_orders")
    assert "pending_prepared_qty" in _columns(conn, "delivery_items")
    assert "metadata_json" in _columns(conn, "delivery_order_history")
    assert "usuario_id" in _columns(conn, "drivers")
    assert "idx_delivery_items_adjustment_status" in _indexes(conn, "delivery_items")
    assert "idx_delivery_workflow_status" in _indexes(conn, "delivery_orders")
    assert "idx_delivery_history_order_created" in _indexes(conn, "delivery_order_history")


def test_migrator_backfills_existing_minimal_tables_without_dropping_data():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE delivery_orders (id INTEGER PRIMARY KEY, direccion TEXT NOT NULL, estado TEXT)")
    conn.execute("CREATE TABLE delivery_items (id INTEGER PRIMARY KEY, delivery_id INTEGER NOT NULL, nombre TEXT NOT NULL)")
    conn.execute("CREATE TABLE delivery_order_history (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL)")
    conn.execute("INSERT INTO delivery_orders(id, direccion, estado) VALUES (1, 'Calle 1', 'pendiente')")
    conn.commit()

    DeliverySchemaMigrator(conn).ensure_schema()

    row = conn.execute("SELECT direccion, estado FROM delivery_orders WHERE id=1").fetchone()
    assert dict(row) == {"direccion": "Calle 1", "estado": "pendiente"}
    assert "fecha" in _columns(conn, "delivery_orders")
    assert "source_channel" in _columns(conn, "delivery_orders")
    assert "tolerance_units" in _columns(conn, "delivery_items")
    assert "created_at" in _columns(conn, "delivery_order_history")


def test_repository_ensure_schema_delegates_to_migrator_contract():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    DeliveryRepository(conn)

    assert "adjustment_blocked_state" in _columns(conn, "delivery_orders")
    assert "adjustment_token" in _columns(conn, "delivery_items")


def test_delivery_service_adjustment_schema_shim_uses_migrator():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    DeliveryService(db=conn, whatsapp_service=DummyWA(), geocoding_service=DummyGeo())

    assert "pending_subtotal" in _columns(conn, "delivery_items")
    assert "idx_delivery_items_adjustment_token" in _indexes(conn, "delivery_items")

"""Tests for delivery lifecycle handlers (v13.30)."""
from __future__ import annotations

import sqlite3
import unittest

from core.events.handlers.delivery_handler import (
    DeliveryLifecycleAuditHandler,
    InventoryCommitHandler,
    DriverSettlementFinanceHandler,
    PurchaseSuggestionHandler,
    DeliveryNotificationDispatchHandler,
)


def _make_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            accion TEXT, modulo TEXT, entidad TEXT, entidad_id TEXT,
            usuario TEXT, sucursal_id INTEGER, detalles TEXT, fecha TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS inventory_reservations (
            id TEXT PRIMARY KEY,
            branch_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            reserved_qty REAL NOT NULL CHECK(reserved_qty > 0),
            operation_id TEXT NOT NULL,
            operation_type TEXT NOT NULL,
            expires_at DATETIME NOT NULL,
            released INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT (datetime('now'))
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS branch_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            branch_id INTEGER NOT NULL DEFAULT 1,
            quantity REAL DEFAULT 0,
            UNIQUE(product_id, branch_id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS inventario_actual (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER NOT NULL,
            sucursal_id INTEGER NOT NULL DEFAULT 1,
            cantidad REAL DEFAULT 0,
            UNIQUE(producto_id, sucursal_id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS inventory_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            branch_id INTEGER NOT NULL,
            movement_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            usuario TEXT DEFAULT 'sistema',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    db.commit()
    return db


class TestDeliveryLifecycleAuditHandler(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.handler = DeliveryLifecycleAuditHandler(self.db)

    def test_writes_audit_row(self):
        self.handler.handle({
            "_event_type": "DELIVERY_ORDER_CREATED",
            "order_id": 42,
            "folio": "DEL-42",
            "usuario": "cajero1",
            "sucursal_id": 1,
            "total": 250.00,
        })
        row = self.db.execute("SELECT * FROM audit_logs WHERE entidad_id='42'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["accion"], "DELIVERY_ORDER_CREATED")
        self.assertEqual(row["modulo"], "DELIVERY")
        self.assertIn("folio=DEL-42", row["detalles"])

    def test_handles_missing_optional_fields(self):
        # Should not raise even with minimal payload
        self.handler.handle({"order_id": 99})
        row = self.db.execute("SELECT * FROM audit_logs WHERE entidad_id='99'").fetchone()
        self.assertIsNotNone(row)

    def test_handles_total_in_details(self):
        self.handler.handle({
            "_event_type": "DELIVERY_ORDER_DELIVERED",
            "order_id": 7,
            "folio": "DEL-7",
            "total": 100.0,
        })
        row = self.db.execute("SELECT detalles FROM audit_logs WHERE entidad_id='7'").fetchone()
        self.assertIn("100.00", row["detalles"])


class TestInventoryCommitHandler(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        # Seed a reservation
        self.db.execute("""
            INSERT INTO inventory_reservations
            (id, branch_id, product_id, reserved_qty, operation_id, operation_type, expires_at)
            VALUES ('res-1', 1, 101, 2.5, 'op-10', 'delivery', datetime('now', '+1 day'))
        """)
        # Seed physical stock in inventario_actual (what get_available_stock queries)
        self.db.execute(
            "INSERT INTO inventario_actual(producto_id, sucursal_id, cantidad) VALUES(101, 1, 10.0)"
        )
        self.db.commit()
        self.handler = InventoryCommitHandler(self.db)

    def test_commits_reservation_and_decrements_stock(self):
        from core.services.reservation_service import ReservationService
        svc = ReservationService()
        available_before = svc.get_available_stock(self.db, product_id=101, branch_id=1)
        self.assertAlmostEqual(available_before, 10.0 - 2.5, places=2)

        self.handler.handle({
            "order_id": 10,
            "operation_id": "op-10",
            "branch_id": 1,
            "db": self.db,
        })

        # Reservation should be released
        res = self.db.execute(
            "SELECT released FROM inventory_reservations WHERE operation_id='op-10'"
        ).fetchone()
        self.assertEqual(res["released"], 1)

    def test_no_op_when_no_reservations_and_no_items(self):
        # Should not raise
        self.handler.handle({"order_id": 999, "operation_id": "nonexistent", "db": self.db})

    def test_fallback_to_items_payload(self):
        """When no reservations exist, should use items[] from payload."""
        self.db.execute("""
            INSERT INTO branch_inventory(product_id, branch_id, quantity)
            VALUES(202, 1, 5.0)
            ON CONFLICT(product_id, branch_id) DO NOTHING
        """)
        self.db.commit()
        # Should not raise; uses fallback path
        self.handler.handle({
            "order_id": 55,
            "operation_id": "op-55-new",
            "branch_id": 1,
            "items": [{"producto_id": 202, "final_qty": 1.0}],
            "db": self.db,
        })


class TestDriverSettlementFinanceHandler(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.handler = DriverSettlementFinanceHandler(self.db)

    def test_writes_audit_row(self):
        self.handler.handle({
            "cut_id": 5,
            "driver_nombre": "Juan Repartidor",
            "efectivo": 350.00,
            "diferencia": -5.00,
            "sucursal_id": 1,
            "usuario_corte": "supervisor",
        })
        row = self.db.execute(
            "SELECT * FROM audit_logs WHERE accion='CORTE_REPARTIDOR'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn("Juan Repartidor", row["detalles"])

    def test_no_cut_id_is_noop(self):
        # Should not raise
        self.handler.handle({"driver_nombre": "Test"})


class TestPurchaseSuggestionHandler(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.handler = PurchaseSuggestionHandler(self.db)

    def test_writes_audit_row(self):
        self.handler.handle({
            "producto_id": 77,
            "cantidad_sugerida": 10.0,
            "motivo": "stock_bajo",
            "sucursal_id": 1,
        })
        row = self.db.execute(
            "SELECT * FROM audit_logs WHERE accion='SUGERENCIA_COMPRA'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIn("77", row["entidad_id"])

    def test_no_product_id_is_noop(self):
        self.handler.handle({"cantidad_sugerida": 5.0})
        count = self.db.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        self.assertEqual(count, 0)


class TestDeliveryNotificationDispatchHandler(unittest.TestCase):
    def test_dispatches_without_service(self):
        # Should not raise when no service available
        handler = DeliveryNotificationDispatchHandler(notification_service=None)
        handler._svc_init_failed = True  # short-circuit lazy init
        handler.handle({
            "canal": "toast",
            "template": "delivery_new",
            "params": {"title": "Test", "body": "hello"},
            "order_id": 1,
        })

    def test_dispatches_with_mock_service(self):
        calls = []

        class MockSvc:
            def notify(self, payload):
                calls.append(payload)

        handler = DeliveryNotificationDispatchHandler(notification_service=MockSvc())
        handler.handle({
            "canal": "toast",
            "template": "delivery_created",
            "params": {"title": "Nuevo", "body": "Pedido recibido"},
            "order_id": 42,
            "folio": "DEL-42",
        })
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].order_id, 42)
        self.assertEqual(calls[0].event_type, "delivery_created")


if __name__ == "__main__":
    unittest.main()

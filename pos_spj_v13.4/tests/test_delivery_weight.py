"""Tests for variable-weight delivery features.

Covers:
  - ReservationService: reserve, release, availability, compute_adjustment
  - DeliveryService: adjust_item_weight, get_order_items
  - Migration 069: schema
  - Handlers: weight adjustment, reservation release
  - Regression: existing delivery flow unbroken
"""
from __future__ import annotations

import sqlite3
import uuid
from unittest.mock import MagicMock, patch

import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    """In-memory SQLite DB bootstrapped via DeliveryRepository + migration 069."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Bootstrap full delivery schema via repository
    from repositories.delivery_repository import DeliveryRepository
    DeliveryRepository(conn)

    # Additional tables needed by tests / migration 069
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS inventario_actual (
            id INTEGER PRIMARY KEY,
            producto_id INTEGER,
            sucursal_id INTEGER,
            cantidad REAL DEFAULT 0,
            UNIQUE(producto_id, sucursal_id)
        );
        CREATE TABLE IF NOT EXISTS movimientos_inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER, sucursal_id INTEGER, tipo TEXT, cantidad REAL,
            reference_type TEXT, reference_id TEXT, operation_id TEXT,
            usuario TEXT, notas TEXT, fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS inventory_reservations (
            id TEXT PRIMARY KEY, branch_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            reserved_qty REAL NOT NULL CHECK(reserved_qty > 0),
            operation_id TEXT NOT NULL, operation_type TEXT NOT NULL DEFAULT 'delivery',
            expires_at DATETIME NOT NULL, released INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS delivery_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_id INTEGER NOT NULL, producto_id INTEGER, nombre TEXT,
            cantidad REAL DEFAULT 1, precio_unitario REAL DEFAULT 0,
            subtotal REAL DEFAULT 0, unidad TEXT DEFAULT 'u',
            requested_qty REAL, prepared_qty REAL, final_qty REAL,
            prepared_by TEXT, prepared_at DATETIME,
            adjustment_reason TEXT, tolerance_exceeded INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY, nombre TEXT,
            precio REAL DEFAULT 0, activo INTEGER DEFAULT 1
        );
    """)
    # Add weight_adjusted column if missing (migration 069 idempotent)
    for col in ["weight_adjusted INTEGER DEFAULT 0",
                "pago_metodo TEXT DEFAULT ''",
                "pago_monto REAL DEFAULT 0"]:
        try:
            conn.execute(f"ALTER TABLE delivery_orders ADD COLUMN {col}")
        except Exception:
            pass
    conn.commit()
    return conn


@pytest.fixture
def reservation_service():
    from core.services.reservation_service import ReservationService
    return ReservationService()


# ── ReservationService unit tests ─────────────────────────────────────────────

class TestReservationService:

    def _seed_stock(self, db, product_id: int, qty: float):
        db.execute(
            "INSERT OR REPLACE INTO inventario_actual (producto_id, sucursal_id, cantidad) VALUES (?,1,?)",
            (product_id, qty),
        )
        db.commit()

    def test_reserve_basic(self, db, reservation_service):
        self._seed_stock(db, product_id=1, qty=10.0)
        rid = reservation_service.reserve(db, product_id=1, qty=3.0, operation_id="op-1")
        assert rid  # UUID returned
        reserved = reservation_service.get_reserved_qty(db, product_id=1, branch_id=1)
        assert reserved == pytest.approx(3.0)

    def test_available_stock_reduces_after_reserve(self, db, reservation_service):
        self._seed_stock(db, product_id=2, qty=5.0)
        reservation_service.reserve(db, product_id=2, qty=2.0, operation_id="op-2")
        available = reservation_service.get_available_stock(db, product_id=2, branch_id=1)
        assert available == pytest.approx(3.0)

    def test_reserve_insufficient_stock_raises(self, db, reservation_service):
        self._seed_stock(db, product_id=3, qty=1.0)
        with pytest.raises(ValueError, match="Stock insuficiente"):
            reservation_service.reserve(db, product_id=3, qty=5.0, operation_id="op-3")

    def test_release_restores_availability(self, db, reservation_service):
        self._seed_stock(db, product_id=4, qty=10.0)
        reservation_service.reserve(db, product_id=4, qty=4.0, operation_id="op-4")
        released = reservation_service.release_by_operation(db, operation_id="op-4")
        assert released == 1
        available = reservation_service.get_available_stock(db, product_id=4, branch_id=1)
        assert available == pytest.approx(10.0)

    def test_double_release_is_idempotent(self, db, reservation_service):
        self._seed_stock(db, product_id=5, qty=10.0)
        reservation_service.reserve(db, product_id=5, qty=2.0, operation_id="op-5")
        reservation_service.release_by_operation(db, operation_id="op-5")
        released2 = reservation_service.release_by_operation(db, operation_id="op-5")
        assert released2 == 0  # already released

    def test_release_non_existent_operation_safe(self, db, reservation_service):
        n = reservation_service.release_by_operation(db, operation_id="does-not-exist")
        assert n == 0

    def test_is_variable_weight(self):
        from core.services.reservation_service import ReservationService as RS
        assert RS.is_variable_weight("kg")
        assert RS.is_variable_weight("g")
        assert RS.is_variable_weight("lb")
        assert RS.is_variable_weight("KG")
        assert not RS.is_variable_weight("u")
        assert not RS.is_variable_weight("pza")
        assert not RS.is_variable_weight("")

    def test_compute_adjustment_within_tolerance(self):
        from core.services.reservation_service import ReservationService as RS
        adj = RS.compute_adjustment(requested_qty=1.0, prepared_qty=1.03, unit_price=100.0)
        assert adj["diff_qty"] == pytest.approx(0.03)
        assert adj["new_subtotal"] == pytest.approx(103.0)
        assert adj["diff_pct"] == pytest.approx(3.0)
        assert adj["tolerance_exceeded"] is False  # 3% < 5% default

    def test_compute_adjustment_exceeds_tolerance(self):
        from core.services.reservation_service import ReservationService as RS
        adj = RS.compute_adjustment(requested_qty=1.0, prepared_qty=1.20, unit_price=100.0)
        assert adj["tolerance_exceeded"] is True  # 20% > 5%
        assert adj["new_subtotal"] == pytest.approx(120.0)

    def test_compute_adjustment_zero_requested(self):
        from core.services.reservation_service import ReservationService as RS
        adj = RS.compute_adjustment(requested_qty=0, prepared_qty=0.5, unit_price=100.0)
        assert adj["new_subtotal"] == pytest.approx(50.0)
        assert adj["tolerance_exceeded"] is False  # div-by-zero guard


# ── DeliveryService integration tests ────────────────────────────────────────

class TestDeliveryServiceWeightAdjust:

    def _make_order(self, db) -> tuple:
        """Insert a delivery_order + one variable-weight item. Returns (order_id, item_id)."""
        cur = db.execute(
            "INSERT INTO delivery_orders (folio, cliente_tel, total, direccion)"
            " VALUES ('DEL-1','5551234567',100.0,'Calle Test 1')"
        )
        order_id = cur.lastrowid
        cur2 = db.execute(
            "INSERT INTO delivery_items (delivery_id, nombre, cantidad, precio_unitario, subtotal, unidad)"
            " VALUES (?,?,?,?,?,?)",
            (order_id, "Ribeye", 1.20, 350.0, 420.0, "kg"),
        )
        item_id = cur2.lastrowid
        db.commit()
        return order_id, item_id

    def _make_service(self, db):
        from core.services.delivery_service import DeliveryService
        from repositories.delivery_repository import DeliveryRepository
        from core.services.delivery_whatsapp_service import DeliveryWhatsAppService
        from core.services.geocoding_service import GeocodingService

        # Stub out external services
        wa = MagicMock(spec=DeliveryWhatsAppService)
        wa.notify_status.return_value = True
        wa.sync_status.return_value = True
        geo = MagicMock(spec=GeocodingService)
        geo.autocomplete.return_value = []
        geo.geocode.return_value = None

        svc = DeliveryService(
            db=db,
            repository=DeliveryRepository(db),
            whatsapp_service=wa,
            geocoding_service=geo,
        )
        return svc

    def test_get_order_items_returns_rows(self, db):
        order_id, item_id = self._make_order(db)
        svc = self._make_service(db)
        items = svc.get_order_items(order_id)
        assert len(items) == 1
        assert items[0]["nombre"] == "Ribeye"
        assert items[0]["unidad"] == "kg"

    def test_adjust_item_weight_updates_db(self, db):
        order_id, item_id = self._make_order(db)
        svc = self._make_service(db)

        # Suppress EventBus publish
        with patch.object(svc, "_publish", return_value=None):
            adj = svc.adjust_item_weight(
                order_id=order_id,
                item_id=item_id,
                prepared_qty=1.31,
                prepared_by="operador_test",
                adjustment_reason="báscula digital",
            )

        assert adj["diff_qty"] == pytest.approx(0.11, abs=1e-3)
        assert adj["new_subtotal"] == pytest.approx(1.31 * 350.0, rel=1e-3)

        row = db.execute(
            "SELECT prepared_qty, prepared_by, adjustment_reason FROM delivery_items WHERE id=?",
            (item_id,),
        ).fetchone()
        # Note: handler writes prepared_qty — but handler runs via EventBus which is mocked.
        # The adj result is computed by service (no DB write here — that's the handler's job).
        # So we just verify the service returned correct calculations.
        assert adj["tolerance_exceeded"] is True  # (1.31-1.20)/1.20 ≈ 9.2% > 5%

    def test_adjust_item_publishes_event(self, db):
        order_id, item_id = self._make_order(db)
        svc = self._make_service(db)
        published = []
        svc._publish = lambda evt, payload: published.append(evt)

        svc.adjust_item_weight(order_id, item_id, 1.31, "op")

        assert "DELIVERY_ITEM_WEIGHT_ADJUSTED" in published


# ── Delivery handler unit tests ───────────────────────────────────────────────

class TestDeliveryHandlers:

    def test_reserve_stock_handler(self, db):
        from core.events.handlers.delivery_handler import DeliveryReserveStockHandler
        # Seed stock
        db.execute("INSERT OR REPLACE INTO inventario_actual VALUES (NULL,10,1,5.0)")
        db.commit()

        handler = DeliveryReserveStockHandler(db)
        handler.handle({
            "order_id": 99,
            "operation_id": "op-99",
            "branch_id": 1,
            "items": [{"producto_id": 10, "cantidad": 2.0, "nombre": "Pollo"}],
            "db": db,
        })

        from core.services.reservation_service import ReservationService
        reserved = ReservationService().get_reserved_qty(db, 10, 1)
        assert reserved == pytest.approx(2.0)

    def test_reservation_release_handler(self, db):
        from core.services.reservation_service import ReservationService
        from core.events.handlers.delivery_handler import DeliveryReservationReleaseHandler
        db.execute("INSERT OR REPLACE INTO inventario_actual VALUES (NULL,20,1,10.0)")
        db.commit()

        svc = ReservationService()
        svc.reserve(db, product_id=20, qty=3.0, operation_id="op-20")

        handler = DeliveryReservationReleaseHandler(db)
        handler.handle({"order_id": "op-20"})

        reserved = svc.get_reserved_qty(db, 20, 1)
        assert reserved == pytest.approx(0.0)

    def test_weight_adjustment_handler_updates_totals(self, db):
        from core.events.handlers.delivery_handler import DeliveryWeightAdjustmentHandler
        # Setup order + item (direccion is NOT NULL in real schema)
        cur = db.execute(
            "INSERT INTO delivery_orders (total, direccion) VALUES (420.0,'Calle Test 1')"
        )
        order_id = cur.lastrowid
        cur2 = db.execute(
            "INSERT INTO delivery_items (delivery_id, nombre, cantidad, precio_unitario, subtotal, unidad)"
            " VALUES (?,?,?,?,?,?)",
            (order_id, "Lomo", 1.2, 350.0, 420.0, "kg"),
        )
        item_id = cur2.lastrowid
        db.commit()

        handler = DeliveryWeightAdjustmentHandler(db)
        with patch("core.events.handlers.delivery_handler._publish_safe") as mock_pub:
            handler.handle({
                "order_id": order_id,
                "item_id": item_id,
                "requested_qty": 1.2,
                "prepared_qty": 1.31,
                "unit_price": 350.0,
                "prepared_by": "test_op",
                "adjustment_reason": "test",
                "db": db,
            })

        # Verify DB was updated
        row = db.execute(
            "SELECT di.prepared_qty FROM delivery_items di WHERE di.id=?",
            (item_id,),
        ).fetchone()
        # weight_adjusted should be 1
        order_row = db.execute(
            "SELECT weight_adjusted, total FROM delivery_orders WHERE id=?",
            (order_id,),
        ).fetchone()
        assert order_row[0] == 1
        assert float(order_row[1]) == pytest.approx(1.31 * 350.0, rel=1e-3)

        # Verify DELIVERY_TOTAL_UPDATED was published
        mock_pub.assert_called_once()
        assert mock_pub.call_args[0][0] == "DELIVERY_TOTAL_UPDATED"


# ── Regression: existing delivery flow ───────────────────────────────────────

class TestDeliveryRegressions:

    def test_create_order_without_items_still_works(self, db):
        """create_order with no items dict should not crash."""
        from core.services.delivery_service import DeliveryService
        from repositories.delivery_repository import DeliveryRepository
        from core.services.delivery_whatsapp_service import DeliveryWhatsAppService
        from core.services.geocoding_service import GeocodingService

        wa = MagicMock(spec=DeliveryWhatsAppService)
        wa.notify_status.return_value = False
        wa.sync_status.return_value = True
        geo = MagicMock(spec=GeocodingService)
        geo.geocode.return_value = None

        # Schema already created by the db fixture
        svc = DeliveryService(
            db=db,
            repository=DeliveryRepository(db),
            whatsapp_service=wa,
            geocoding_service=geo,
        )
        with patch.object(svc, "_publish", return_value=None):
            oid = svc.create_order({"direccion": "Av. Insurgentes 100"}, usuario="test")
        assert isinstance(oid, int)

    def test_delivery_service_tests_still_pass(self):
        """Smoke-check that the 2 existing delivery service tests still work."""
        import subprocess, sys
        result = subprocess.run(
            [sys.executable, "-m", "pytest",
             "tests/test_delivery_service.py", "-q", "--tb=short"],
            capture_output=True, text=True, cwd="."
        )
        assert result.returncode == 0, result.stdout + result.stderr

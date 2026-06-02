import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "whatsapp_service"))

from core.delivery.application.change_delivery_status import ChangeDeliveryStatusUseCase
from core.delivery.application.create_delivery_order import CreateDeliveryOrderUseCase
from core.delivery.application.process_delivery_outbox import ProcessDeliveryOutboxUseCase
from core.delivery.infrastructure.delivery_outbox_repository import DeliveryOutboxRepository
from core.delivery.infrastructure.inventory_reservation_adapter import ReservationServiceInventoryAdapter
from core.delivery.projections.delivery_inventory_projection import DeliveryInventoryProjectionService
from core.delivery.projections.sale_delivery_projection import SaleDeliveryProjectionService
from core.services.delivery_service import DeliveryService
from core.services.order_total_service import OrderTotalService
from erp.adjustment_approval import AdjustmentApprovalService
from repositories.delivery_repository import DeliveryRepository


class DummyGeo:
    def __init__(self):
        self.calls = []

    def geocode(self, address):
        self.calls.append(address)
        return {"lat": 20.1, "lng": -103.2}

    def autocomplete(self, _query):
        return []


class DummyWA:
    def __init__(self, pulled=None):
        self.pulled = pulled or []
        self.notifications = []
        self.synced = []

    def notify_status(self, **kwargs):
        self.notifications.append(kwargs)
        return True

    def sync_status(self, whatsapp_order_id, status):
        self.synced.append((whatsapp_order_id, status))
        return True

    def pull_orders(self):
        return list(self.pulled)


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    repo = DeliveryRepository(db)
    db.execute("CREATE TABLE ventas(id INTEGER PRIMARY KEY, estado TEXT, total REAL, workflow_type TEXT, canal TEXT, direccion TEXT)")
    db.execute(
        """
        CREATE TABLE detalles_venta(
            id INTEGER PRIMARY KEY,
            venta_id INTEGER,
            producto_id INTEGER,
            producto_nombre TEXT,
            cantidad REAL,
            precio_unitario REAL,
            subtotal REAL
        )
        """
    )
    return db, repo


def _seed_order(
    db,
    *,
    order_id=1,
    venta_id=1,
    estado="pendiente",
    workflow_type="delivery",
    delivery_type="home_delivery",
    total=200,
    phone="5512345678",
):
    db.execute(
        "INSERT OR IGNORE INTO ventas(id, estado, total, workflow_type, canal, direccion) VALUES (?, ?, ?, ?, 'whatsapp', 'Calle 1')",
        (venta_id, estado, total, workflow_type),
    )
    db.execute(
        """
        INSERT INTO delivery_orders(id, venta_id, folio, whatsapp_order_id, cliente_tel, direccion, estado, total, workflow_type, delivery_type)
        VALUES (?, ?, ?, ?, ?, 'Calle 1', ?, ?, ?, ?)
        """,
        (order_id, venta_id, f"DEL-{order_id}", f"wa-{order_id}", phone, estado, total, workflow_type, delivery_type),
    )
    db.execute(
        """
        INSERT INTO delivery_items(id, delivery_id, nombre, producto_id, cantidad, precio_unitario, subtotal, unidad, prepared_qty, final_qty)
        VALUES (?, ?, 'Pollo', 10, 2.0, 100, 200, 'kg', 2.0, 2.0)
        """,
        (order_id, order_id),
    )
    db.commit()


def _inventory_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    DeliveryRepository(db)
    db.execute("CREATE TABLE productos(id INTEGER PRIMARY KEY, nombre TEXT, existencia REAL DEFAULT 0, precio_compra REAL DEFAULT 0)")
    db.execute(
        """
        CREATE TABLE inventario_actual(
            producto_id INTEGER,
            sucursal_id INTEGER,
            cantidad REAL,
            costo_promedio REAL DEFAULT 0,
            ultima_actualizacion TEXT,
            PRIMARY KEY(producto_id, sucursal_id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE branch_inventory(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            branch_id INTEGER,
            quantity REAL,
            batch_id INTEGER,
            updated_at TEXT
        )
        """
    )
    db.execute(
        """
        CREATE TABLE movimientos_inventario(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid TEXT,
            producto_id INTEGER,
            sucursal_id INTEGER,
            tipo_movimiento TEXT,
            referencia_tipo TEXT,
            referencia_id TEXT,
            cantidad REAL,
            costo_unitario REAL,
            operation_id TEXT,
            usuario TEXT,
            nota TEXT
        )
        """
    )
    db.execute("INSERT INTO productos(id, nombre, existencia, precio_compra) VALUES (10, 'Pollo', 20, 20)")
    db.execute("INSERT INTO inventario_actual(producto_id, sucursal_id, cantidad, costo_promedio) VALUES (10, 1, 20, 20)")
    db.commit()
    return db


def test_create_order_required_contract_and_whatsapp_dedupe():
    db, repo = _db()
    geo = DummyGeo()
    outbox = DeliveryOutboxRepository(db)

    with pytest.raises(ValueError, match="dirección"):
        CreateDeliveryOrderUseCase(db=db, repository=repo).execute({"direccion": " "})

    order_id = CreateDeliveryOrderUseCase(
        db=db,
        repository=repo,
        geocoding_service=geo,
        whatsapp_service=DummyWA(),
        outbox_repository=outbox,
    ).execute(
        {
            "whatsapp_order_id": "wa-create-1",
            "venta_id": 100,
            "direccion": "Calle Crear",
            "cliente_tel": "55",
            "items": [{"producto_id": 10, "nombre": "Pollo", "cantidad": 2, "precio_unitario": 100}],
        },
        usuario="tester",
    )

    assert geo.calls == ["Calle Crear"]
    assert repo.get_order(order_id)["lat"] == 20.1
    assert db.execute("SELECT COUNT(*) FROM delivery_items WHERE delivery_id=?", (order_id,)).fetchone()[0] == 1
    event_types = {row[0] for row in db.execute("SELECT event_type FROM delivery_outbox_events WHERE aggregate_id=?", (order_id,)).fetchall()}
    assert {"DELIVERY_ORDER_RESERVED", "CUSTOMER_NOTIFICATION_REQUESTED"} <= event_types

    repo.upsert_order_from_whatsapp({"whatsapp_order_id": "wa-dup", "venta_id": 101, "direccion": "Dir A"})
    repo.upsert_order_from_whatsapp({"whatsapp_order_id": "wa-dup", "venta_id": 101, "direccion": "Dir B"})
    repo.upsert_order_from_whatsapp({"venta_id": 102, "direccion": "Dir C"})
    repo.upsert_order_from_whatsapp({"venta_id": 102, "direccion": "Dir D"})
    assert db.execute("SELECT COUNT(*) FROM delivery_orders WHERE whatsapp_order_id='wa-dup'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM delivery_orders WHERE venta_id=102").fetchone()[0] == 1


def test_change_status_required_transition_matrix():
    db, repo = _db()
    uc = lambda: ChangeDeliveryStatusUseCase(db=db, repository=repo, sale_projection=SaleDeliveryProjectionService(db), whatsapp_service=DummyWA())

    _seed_order(db, order_id=1, estado="pendiente", workflow_type="delivery")
    uc().execute(1, "preparacion", usuario="tester")
    assert repo.get_order(1)["estado"] == "preparacion"
    uc().execute(1, "en_ruta", usuario="tester")
    assert repo.get_order(1)["estado"] == "en_ruta"

    _seed_order(db, order_id=2, venta_id=2, estado="preparacion", workflow_type="counter", delivery_type="pickup")
    uc().execute(2, "entregado", usuario="tester", responsable="mostrador")
    assert repo.get_order(2)["estado"] == "entregado"

    _seed_order(db, order_id=3, venta_id=3, estado="preparacion", workflow_type="counter", delivery_type="pickup")
    with pytest.raises(ValueError, match="mostrador"):
        uc().execute(3, "en_ruta", usuario="tester")

    _seed_order(db, order_id=4, venta_id=4, estado="programado", workflow_type="scheduled")
    with pytest.raises(ValueError, match="programado"):
        uc().execute(4, "preparacion", usuario="tester")

    _seed_order(db, order_id=5, venta_id=5, estado="en_ruta", workflow_type="delivery")
    with pytest.raises(ValueError, match="responsable"):
        uc().execute(5, "entregado", usuario="tester")

    _seed_order(db, order_id=6, venta_id=6, estado="preparacion", workflow_type="delivery")
    db.execute("UPDATE delivery_items SET adjustment_status='pending_customer' WHERE delivery_id=6")
    db.commit()
    with pytest.raises(ValueError, match="ajuste"):
        uc().execute(6, "en_ruta", usuario="tester")
    with pytest.raises(ValueError, match="ajuste"):
        uc().execute(6, "entregado", usuario="tester", responsable="r1")


def test_inventory_required_reserve_release_commit_and_idempotency():
    db = _inventory_db()
    projection = DeliveryInventoryProjectionService(ReservationServiceInventoryAdapter(db))

    reserved = projection.handle_order_reserved({
        "order_id": 10,
        "operation_id": "delivery:10",
        "items": [{"id": 1, "producto_id": 10, "cantidad": 2}],
        "branch_id": 1,
    })
    assert reserved["reserved"] == 1

    released = projection.handle_inventory_release_required({"order_id": 10, "operation_id": "delivery:10", "reason": "cancelado"})
    assert released["released"] == 1

    projection.handle_order_reserved({
        "order_id": 11,
        "operation_id": "delivery:11",
        "items": [{"id": 7, "producto_id": 10, "cantidad": 3}],
        "branch_id": 1,
    })
    payload = {
        "order_id": 11,
        "operation_id": "delivery:11",
        "items": [{"id": 7, "producto_id": 10, "cantidad": 3, "prepared_qty": 2.5, "final_qty": 2.25}],
        "branch_id": 1,
    }
    first = projection.handle_inventory_commit_required(payload)
    second = projection.handle_inventory_commit_required(payload)
    assert first["committed"] == 1
    assert second["committed"] == 0
    assert db.execute("SELECT COUNT(*) FROM movimientos_inventario WHERE operation_id='delivery:11:item:7:commit'").fetchone()[0] == 1


def test_weight_adjustment_required_accept_reject_and_route_blocking():
    db, repo = _db()
    _seed_order(db, order_id=1, estado="preparacion")
    svc = DeliveryService(db=db, repository=repo, whatsapp_service=DummyWA(), geocoding_service=DummyGeo())
    svc._publish = lambda *_args, **_kwargs: None

    auto = svc.adjust_item_weight(1, 1, 2.1, "op")
    assert auto["applied"] is True
    assert repo.get_order(1)["total"] == 210.0

    _seed_order(db, order_id=2, venta_id=2, estado="preparacion", phone="5599999999")
    pending = svc.adjust_item_weight(2, 2, 2.3, "op")
    assert pending["applied"] is False
    assert db.execute("SELECT pending_prepared_qty FROM delivery_items WHERE id=2").fetchone()[0] == 2.3
    with pytest.raises(ValueError, match="ajuste"):
        svc.update_status(2, "en_ruta", usuario="tester")
    accepted = AdjustmentApprovalService(db).respond_latest_for_phone("5599999999", accepted=True)
    assert accepted["total"] == 230.0
    assert db.execute("SELECT cantidad, adjustment_status FROM delivery_items WHERE id=2").fetchone()[0] == 2.3

    _seed_order(db, order_id=3, venta_id=3, estado="preparacion", phone="5588888888")
    svc.adjust_item_weight(3, 3, 2.3, "op")
    rejected = AdjustmentApprovalService(db).respond_latest_for_phone("5588888888", accepted=False)
    item = db.execute("SELECT cantidad, subtotal, adjustment_status FROM delivery_items WHERE id=3").fetchone()
    assert rejected["total"] == 200.0
    assert item["cantidad"] == 2.0
    assert item["subtotal"] == 200.0
    assert item["adjustment_status"] == "rejected"


def test_totals_required_recalculate_from_items_single_sale_projection_and_total_updated_event():
    db, repo = _db()
    _seed_order(db, order_id=1, estado="preparacion")
    db.execute("INSERT INTO delivery_items(id, delivery_id, nombre, cantidad, precio_unitario, subtotal) VALUES (20, 1, 'Salsa', 1, 15, 15)")
    db.commit()

    total = OrderTotalService(db).recalculate_order_total(1)
    assert total == 215.0
    assert db.execute("SELECT total FROM ventas WHERE id=1").fetchone()[0] == 200.0

    update_ventas_total_count = {"n": 0}
    def _trace(sql):
        normalized = " ".join(sql.upper().split())
        if normalized.startswith("UPDATE VENTAS SET TOTAL"):
            update_ventas_total_count["n"] += 1
    db.set_trace_callback(_trace)

    svc = DeliveryService(db=db, repository=repo, whatsapp_service=DummyWA(), geocoding_service=DummyGeo())
    svc._publish = lambda *_args, **_kwargs: None
    svc.adjust_item_weight(1, 1, 2.05, "op")
    db.set_trace_callback(None)

    assert update_ventas_total_count["n"] == 1
    row = db.execute("SELECT payload_json FROM delivery_outbox_events WHERE event_type='DELIVERY_TOTAL_UPDATED' AND aggregate_id=1").fetchone()
    assert row is not None
    assert '"new_total"' in row["payload_json"]


def test_outbox_required_transaction_processing_retry_and_no_duplicate_processing():
    db, _repo = _db()
    outbox = DeliveryOutboxRepository(db)
    first = outbox.enqueue(event_type="OK", aggregate_id=1, payload={"order_id": 1, "db": db}, operation_id="op:1", commit=True)
    duplicate = outbox.enqueue(event_type="OK", aggregate_id=1, payload={"order_id": 1}, operation_id="op:1", commit=True)
    fail_id = outbox.enqueue(event_type="FAIL", aggregate_id=1, payload={"order_id": 1}, operation_id="op:fail", commit=True)
    handled = []

    assert first == duplicate
    assert outbox.payload_for(first) == {"order_id": 1}

    result = ProcessDeliveryOutboxUseCase(
        outbox_repository=outbox,
        handlers={
            "OK": lambda payload: handled.append(payload["order_id"]),
            "FAIL": lambda _payload: (_ for _ in ()).throw(RuntimeError("boom")),
        },
    ).execute(limit=10)
    second = ProcessDeliveryOutboxUseCase(
        outbox_repository=outbox,
        handlers={
            "OK": lambda payload: handled.append(payload["order_id"]),
            "FAIL": lambda _payload: (_ for _ in ()).throw(RuntimeError("boom")),
        },
    ).execute(limit=10)

    ok = db.execute("SELECT status FROM delivery_outbox_events WHERE id=?", (first,)).fetchone()[0]
    fail = db.execute("SELECT status, retries, last_error FROM delivery_outbox_events WHERE id=?", (fail_id,)).fetchone()
    assert result == {"processed": 1, "failed": 1}
    assert second == {"processed": 0, "failed": 1}
    assert handled == [1]
    assert ok == "done"
    assert fail["status"] == "pending"
    assert fail["retries"] == 2
    assert "boom" in fail["last_error"]


def test_delivery_service_legacy_compatibility_required_api_surface():
    db, repo = _db()
    svc = DeliveryService(db=db, repository=repo, whatsapp_service=DummyWA(), geocoding_service=DummyGeo())
    for name in ("create_order", "update_status", "adjust_item_weight", "list_orders"):
        assert callable(getattr(svc, name))

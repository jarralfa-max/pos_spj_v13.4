import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
import sqlite3

from erp.adjustment_approval import AdjustmentApprovalService


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE delivery_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folio TEXT,
            venta_id INTEGER,
            total REAL,
            cliente_tel TEXT,
            cliente_nombre TEXT,
            sucursal_id INTEGER DEFAULT 1,
            adjustment_pending INTEGER DEFAULT 1,
            adjustment_blocked_state TEXT DEFAULT 'en_ruta'
        );
        CREATE TABLE delivery_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_id INTEGER,
            cantidad REAL,
            precio_unitario REAL,
            subtotal REAL,
            pending_prepared_qty REAL,
            pending_subtotal REAL,
            prepared_qty REAL,
            final_qty REAL,
            adjustment_status TEXT,
            adjustment_response TEXT,
            adjustment_responded_at TEXT,
            tolerance_exceeded INTEGER DEFAULT 1,
            adjustment_requested_at TEXT
        );
        CREATE TABLE ventas (id INTEGER PRIMARY KEY, total REAL);
        CREATE TABLE wa_event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            data_json TEXT,
            sucursal_id INTEGER,
            prioridad INTEGER,
            timestamp TEXT
        );
        """
    )
    return db


def test_accept_adjustment_applies_new_qty_and_total_and_event():
    db = _db()
    db.execute("INSERT INTO ventas(id,total) VALUES (10,200)")
    db.execute("INSERT INTO delivery_orders(id,folio,venta_id,total,cliente_tel,sucursal_id) VALUES (1,'DEL-1',10,200,'+52 55 1234 5678',1)")
    db.execute("INSERT INTO delivery_items(delivery_id,cantidad,precio_unitario,subtotal,pending_prepared_qty,pending_subtotal,adjustment_status,adjustment_requested_at) VALUES (1,2.0,100,200,2.25,225,'pending_customer',datetime('now'))")
    db.commit()

    svc = AdjustmentApprovalService(db)
    out = svc.respond_latest_for_phone("5215512345678", accepted=True)

    assert out["ok"] is True
    assert out["total"] == 225.0
    item = db.execute("SELECT cantidad, subtotal, adjustment_status FROM delivery_items WHERE delivery_id=1").fetchone()
    assert float(item["cantidad"]) == 2.25
    assert float(item["subtotal"]) == 225.0
    assert item["adjustment_status"] == "accepted"

    order = db.execute("SELECT total, adjustment_pending, adjustment_blocked_state FROM delivery_orders WHERE id=1").fetchone()
    assert float(order["total"]) == 225.0
    assert int(order["adjustment_pending"]) == 0
    assert order["adjustment_blocked_state"] == ""

    event = db.execute("SELECT event_type FROM wa_event_log ORDER BY id DESC LIMIT 1").fetchone()
    assert event["event_type"] == "DELIVERY_ADJUSTMENT_ACCEPTED"


def test_reject_adjustment_keeps_original_total_and_event():
    db = _db()
    db.execute("INSERT INTO ventas(id,total) VALUES (20,200)")
    db.execute("INSERT INTO delivery_orders(id,folio,venta_id,total,cliente_tel,sucursal_id) VALUES (2,'DEL-2',20,200,'5512345678',1)")
    db.execute("INSERT INTO delivery_items(delivery_id,cantidad,precio_unitario,subtotal,pending_prepared_qty,pending_subtotal,adjustment_status,adjustment_requested_at) VALUES (2,2.0,100,200,2.25,225,'pending_customer',datetime('now'))")
    db.commit()

    svc = AdjustmentApprovalService(db)
    out = svc.respond_latest_for_phone("55 1234 5678", accepted=False)

    assert out["ok"] is True
    assert out["total"] == 200.0
    item = db.execute("SELECT cantidad, subtotal, adjustment_status FROM delivery_items WHERE delivery_id=2").fetchone()
    assert float(item["cantidad"]) == 2.0
    assert float(item["subtotal"]) == 200.0
    assert item["adjustment_status"] == "rejected"

    event = db.execute("SELECT event_type FROM wa_event_log ORDER BY id DESC LIMIT 1").fetchone()
    assert event["event_type"] == "DELIVERY_ADJUSTMENT_REJECTED"

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))
import sqlite3

from whatsapp_service.erp.pos_notifier import POSNotifier


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, usuario TEXT, nombre TEXT, rol TEXT, sucursal_id INTEGER, activo INTEGER)")
    db.execute("INSERT INTO usuarios(id,usuario,nombre,rol,sucursal_id,activo) VALUES (1,'admin','Admin','admin',1,1)")
    return db


def _db_two_branches_no_roles():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, usuario TEXT, nombre TEXT, rol TEXT, sucursal_id INTEGER, activo INTEGER)")
    db.execute("INSERT INTO usuarios(id,usuario,nombre,rol,sucursal_id,activo) VALUES (1,'u1','U1','',1,1)")
    db.execute("INSERT INTO usuarios(id,usuario,nombre,rol,sucursal_id,activo) VALUES (2,'u2','U2','',2,1)")
    return db


def test_pos_notifier_uses_dedupe_key_per_recipient():
    db = _db()
    notifier = POSNotifier(db)

    kwargs = dict(
        venta_id=101,
        folio='WA-TEST-101',
        cliente_id=1,
        cliente_nombre='Cliente',
        total=200.0,
        sucursal_id=1,
        tipo_entrega='sucursal',
        direccion='',
        items=[],
    )
    notifier.notify_new_whatsapp_order(**kwargs)
    notifier.notify_new_whatsapp_order(**kwargs)

    count = db.execute("SELECT COUNT(*) FROM notification_inbox").fetchone()[0]
    assert count == 1

    row = db.execute("SELECT dedupe_key, severity FROM notification_inbox LIMIT 1").fetchone()
    assert row["dedupe_key"] == "new_order:101:emp:1"
    assert row["severity"] == "info"


def test_pos_notifier_writes_canonical_event_names():
    db = _db()
    notifier = POSNotifier(db)
    notifier.notify_new_whatsapp_order(
        venta_id=202,
        folio='WA-TEST-202',
        cliente_id=1,
        cliente_nombre='Cliente',
        total=150.0,
        sucursal_id=1,
        tipo_entrega='domicilio',
    )

    event_types = {r[0] for r in db.execute("SELECT event_type FROM wa_event_log").fetchall()}
    assert "WHATSAPP_ORDER_CREATED" in event_types
    assert "BRANCH_NOTIFICATION_CREATED" in event_types


def test_pos_notifier_does_not_notify_other_branch_users():
    db = _db_two_branches_no_roles()
    notifier = POSNotifier(db)
    notifier.notify_new_whatsapp_order(
        venta_id=303,
        folio='WA-TEST-303',
        cliente_id=1,
        cliente_nombre='Cliente',
        total=300.0,
        sucursal_id=1,
        tipo_entrega='domicilio',
    )

    rows = db.execute("SELECT empleado_id, sucursal_id FROM notification_inbox ORDER BY empleado_id").fetchall()
    assert len(rows) == 1
    assert rows[0]["empleado_id"] == 1
    assert rows[0]["sucursal_id"] == 1


def test_scheduled_order_notification_uses_warning_and_canonical_event():
    db = _db()
    notifier = POSNotifier(db)
    notifier.notify_scheduled_whatsapp_order(
        venta_id=303,
        folio='WA-TEST-303',
        cliente_id=1,
        cliente_nombre='Cliente',
        total=500.0,
        sucursal_id=1,
        tipo_entrega='domicilio',
        scheduled_at='2026-06-01 09:00:00',
    )

    row = db.execute("SELECT severity, dedupe_key, titulo FROM notification_inbox ORDER BY id DESC LIMIT 1").fetchone()
    assert row["severity"] == "warning"
    assert row["dedupe_key"] == "scheduled_order:303:emp:1"
    assert "programado" in row["titulo"].lower()

    events = {r[0] for r in db.execute("SELECT event_type FROM wa_event_log").fetchall()}
    assert "WHATSAPP_SCHEDULED_ORDER_CREATED" in events


def test_pos_notifier_event_payload_contains_canonical_aliases():
    import json
    db = _db()
    notifier = POSNotifier(db)
    notifier.notify_new_whatsapp_order(
        venta_id=404,
        folio='WA-TEST-404',
        cliente_id=77,
        cliente_nombre='Cliente Alias',
        total=99.0,
        sucursal_id=2,
        tipo_entrega='domicilio',
    )

    row = db.execute(
        "SELECT data_json FROM wa_event_log WHERE event_type='WHATSAPP_ORDER_CREATED' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    payload = json.loads(row[0])
    assert payload["sale_id"] == 404
    assert payload["branch_id"] == 2
    assert payload["customer_id"] == 77
    assert payload["delivery_type"] == "home_delivery"
    assert payload["workflow_type"] == "delivery"
    assert payload["source_channel"] == "whatsapp"

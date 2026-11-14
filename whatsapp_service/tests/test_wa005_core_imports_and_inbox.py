"""SDLC-WA-005: el microservicio no importa `core.*` (paquete eliminado), la
bandeja del POS recibe avisos con id UUIDv7 y la respuesta "no acepto" a un
ajuste de peso se registra como rechazo.

Los esquemas replican las tablas reales del ERP: ids TEXT NOT NULL (UUIDv7).
Las pruebas anteriores usaban INTEGER AUTOINCREMENT y ocultaban el defecto.
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import uuid
from types import SimpleNamespace

import pytest

ORDER_ID = "0192f0a0-0000-7000-8000-0000000000a1"
SALE_ID = "0192f0a0-0000-7000-8000-0000000000b1"
ITEM_ID = "0192f0a0-0000-7000-8000-0000000000c1"
BRANCH_ID = "0192f0a0-0000-7000-8000-0000000000d1"


def _is_uuid7(value) -> bool:
    try:
        return uuid.UUID(str(value)).version == 7
    except ValueError:
        return False


def _delivery_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE delivery_orders (
            id TEXT NOT NULL PRIMARY KEY, folio TEXT, venta_id TEXT, total REAL,
            cliente_tel TEXT, cliente_nombre TEXT, sucursal_id TEXT,
            adjustment_pending INTEGER DEFAULT 1, adjustment_blocked_state TEXT DEFAULT 'en_ruta',
            weight_adjusted INTEGER DEFAULT 0
        );
        CREATE TABLE delivery_items (
            id TEXT NOT NULL PRIMARY KEY, delivery_id TEXT, cantidad REAL, precio_unitario REAL,
            subtotal REAL, pending_prepared_qty REAL, pending_subtotal REAL, prepared_qty REAL,
            final_qty REAL, adjustment_status TEXT, adjustment_response TEXT,
            adjustment_responded_at TEXT, tolerance_exceeded INTEGER DEFAULT 1,
            adjustment_requested_at TEXT
        );
        CREATE TABLE ventas (id TEXT NOT NULL PRIMARY KEY, total REAL);
        CREATE TABLE wa_event_log (
            id TEXT NOT NULL PRIMARY KEY, event_type TEXT NOT NULL, data_json TEXT,
            sucursal_id TEXT, prioridad INTEGER DEFAULT 5, timestamp TEXT
        );
        """
    )
    db.execute("INSERT INTO ventas VALUES (?, 200)", (SALE_ID,))
    db.execute(
        "INSERT INTO delivery_orders(id, folio, venta_id, total, cliente_tel, sucursal_id) "
        "VALUES (?, 'DEL-1', ?, 200, '+52 55 1234 5678', ?)",
        (ORDER_ID, SALE_ID, BRANCH_ID),
    )
    db.execute(
        "INSERT INTO delivery_items(id, delivery_id, cantidad, precio_unitario, subtotal, "
        "pending_prepared_qty, pending_subtotal, adjustment_status, adjustment_requested_at) "
        "VALUES (?, ?, 2.0, 100, 200, 2.25, 225, 'pending_customer', datetime('now'))",
        (ITEM_ID, ORDER_ID),
    )
    db.commit()
    return db


def test_channel_has_no_core_imports():
    import ast
    from pathlib import Path

    channel = Path(__file__).resolve().parents[1]
    offenders = []
    for path in channel.rglob("*.py"):
        if "tests" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "core":
                offenders.append(f"{path.name}:{node.lineno}")
            if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "core" for a in node.names):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []


def test_accepting_an_adjustment_recalculates_and_logs_with_uuid_ids():
    from whatsapp_service.erp.adjustment_approval import AdjustmentApprovalService

    db = _delivery_db()
    out = AdjustmentApprovalService(db).respond_latest_for_phone("5215512345678", accepted=True)

    assert out["ok"] is True
    assert str(out["total"]) == "225.00"
    order = db.execute(
        "SELECT total, adjustment_pending, weight_adjusted FROM delivery_orders WHERE id=?",
        (ORDER_ID,),
    ).fetchone()
    assert float(order["total"]) == 225.0
    assert order["adjustment_pending"] == 0
    assert order["weight_adjusted"] == 1
    assert float(db.execute("SELECT total FROM ventas WHERE id=?", (SALE_ID,)).fetchone()[0]) == 225.0

    events = db.execute("SELECT id, event_type, sucursal_id FROM wa_event_log").fetchall()
    assert {e["event_type"] for e in events} == {
        "DELIVERY_TOTAL_UPDATED", "DELIVERY_ADJUSTMENT_ACCEPTED",
    }
    assert all(_is_uuid7(e["id"]) for e in events)
    assert all(e["sucursal_id"] == BRANCH_ID for e in events)


def test_rejecting_an_adjustment_keeps_the_original_total():
    from whatsapp_service.erp.adjustment_approval import AdjustmentApprovalService

    db = _delivery_db()
    out = AdjustmentApprovalService(db).respond_latest_for_phone("55 1234 5678", accepted=False)

    assert out["ok"] is True
    assert str(out["total"]) == "200.00"
    item = db.execute("SELECT adjustment_status FROM delivery_items WHERE id=?", (ITEM_ID,)).fetchone()
    assert item["adjustment_status"] == "rejected"
    types = {r[0] for r in db.execute("SELECT event_type FROM wa_event_log")}
    assert "DELIVERY_ADJUSTMENT_REJECTED" in types


def test_failed_adjustment_rolls_back_instead_of_leaving_half_applied(monkeypatch):
    from whatsapp_service.erp.adjustment_approval import AdjustmentApprovalService

    db = _delivery_db()
    db.execute("ALTER TABLE wa_event_log RENAME TO wa_event_log_old")
    db.commit()

    with pytest.raises(sqlite3.Error):
        AdjustmentApprovalService(db).respond_latest_for_phone("5512345678", accepted=True)

    item = db.execute("SELECT adjustment_status FROM delivery_items WHERE id=?", (ITEM_ID,)).fetchone()
    assert item["adjustment_status"] == "pending_customer"
    total = db.execute("SELECT total FROM delivery_orders WHERE id=?", (ORDER_ID,)).fetchone()[0]
    assert float(total) == 200.0


@pytest.mark.parametrize(
    "text,expected",
    [
        ("no acepto", False),
        ("No acepto el ajuste", False),
        ("rechazo", False),
        ("acepto", True),
        ("sí acepto", True),
        ("aceptar ajuste", True),
    ],
)
def test_adjustment_reply_is_classified_correctly(monkeypatch, text, expected):
    from whatsapp_service.router import message_router as mr

    seen = []

    class _FakeService:
        def __init__(self, db):
            pass

        def has_pending_for_phone(self, phone):
            return True

        def respond_latest_for_phone(self, phone, accepted):
            seen.append(accepted)
            return {"ok": True, "folio": "DEL-1", "total": "200.00"}

    async def _send_text(*args, **kwargs):
        return None

    monkeypatch.setattr("whatsapp_service.erp.adjustment_approval.AdjustmentApprovalService", _FakeService)
    monkeypatch.setattr(mr, "send_text", _send_text)
    router = SimpleNamespace(erp=SimpleNamespace(db=None))
    msg = SimpleNamespace(text=text, interactive_title=None, from_number="5215512345678")

    handled = asyncio.run(mr.MessageRouter._handle_adjustment_response(router, msg))

    assert handled is True
    assert seen == [expected]


def _inbox_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE usuarios (id TEXT PRIMARY KEY, usuario TEXT, nombre TEXT, rol TEXT, "
        "sucursal_id TEXT, activo INTEGER)"
    )
    db.execute(
        "INSERT INTO usuarios VALUES ('0192f0a0-0000-7000-8000-0000000000e1', 'admin', "
        "'Admin', 'admin', ?, 1)",
        (BRANCH_ID,),
    )
    # Tabla real: migraciones 041 + 089.
    db.execute(
        """
        CREATE TABLE notification_inbox (
            id TEXT NOT NULL PRIMARY KEY, empleado_id TEXT NOT NULL, tipo TEXT NOT NULL,
            titulo TEXT NOT NULL, cuerpo TEXT DEFAULT '', datos TEXT DEFAULT '{}',
            leido INTEGER DEFAULT 0, sucursal_id TEXT, created_at TEXT DEFAULT (datetime('now')),
            leido_at TEXT, dedupe_key TEXT, severity TEXT DEFAULT 'info'
        )
        """
    )
    db.commit()
    return db


def _notify(notifier):
    notifier.notify_new_whatsapp_order(
        venta_id=SALE_ID, folio="WA-1", cliente_id="c1", cliente_nombre="Cliente",
        total="200.00", sucursal_id=BRANCH_ID, tipo_entrega="sucursal", direccion="", items=[],
    )


def test_pos_inbox_receives_the_notification_with_a_uuid7_id():
    from whatsapp_service.erp.pos_notifier import POSNotifier

    db = _inbox_db()
    _notify(POSNotifier(db))

    rows = db.execute("SELECT id, empleado_id FROM notification_inbox").fetchall()
    assert len(rows) == 1
    assert _is_uuid7(rows[0]["id"])


def test_fallback_inbox_table_uses_uuid_text_identity():
    from whatsapp_service.erp.pos_notifier import POSNotifier

    db = _inbox_db()
    db.execute("ALTER TABLE notification_inbox RENAME TO notification_inbox_real")
    db.commit()
    _notify(POSNotifier(db))

    columns = {r[1]: r[2].upper() for r in db.execute("PRAGMA table_info(notification_inbox)")}
    assert columns["id"] == "TEXT"
    row = db.execute("SELECT id FROM notification_inbox").fetchone()
    assert _is_uuid7(row["id"])


def test_failed_inbox_insert_is_logged_as_error(caplog):
    from whatsapp_service.erp.pos_notifier import POSNotifier

    db = _inbox_db()
    db.execute("CREATE TRIGGER no_inbox BEFORE INSERT ON notification_inbox "
               "BEGIN SELECT RAISE(ABORT, 'bandeja bloqueada'); END")
    db.commit()

    with caplog.at_level(logging.ERROR, logger="wa.pos_notifier"):
        _notify(POSNotifier(db))

    assert any(r.levelno == logging.ERROR and "bandeja bloqueada" in r.getMessage()
               for r in caplog.records)

"""Auditoría de caja sobre el canal canónico único CASH_*.

Regresión: el handler anterior hacía `INSERT OR IGNORE INTO audit_logs` SIN
`id`; con audit_logs.id TEXT NOT NULL (born-clean) la fila se descartaba en
silencio y ningún evento de caja quedaba auditado. El test previo lo ocultaba
usando una tabla sintética con INTEGER AUTOINCREMENT — aquí se usa el schema real.
"""
from __future__ import annotations

import pytest

from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid
from core.events.event_bus import EventBus
from core.events.handlers.cash_audit_handler import (
    CASH_AUDIT_EVENTS,
    register_cash_audit,
)
from tests.integration._born_clean_db import make_db


_LEGACY = ("CAJA_TURNO_ABIERTO", "CAJA_MOVIMIENTO",
           "CAJA_CORTE_Z_GENERADO", "CAJA_DIFERENCIA_DETECTADA")


@pytest.fixture()
def bus():
    """EventBus es singleton de proceso: aislar los canales de caja."""
    b = EventBus()
    for evento in CASH_AUDIT_EVENTS + _LEGACY:
        b.clear_handlers(evento)
    yield b
    for evento in CASH_AUDIT_EVENTS + _LEGACY:
        b.clear_handlers(evento)


def _audit_rows(conn):
    return conn.execute(
        "SELECT id, accion, modulo, entidad_id, usuario, sucursal_id, detalles"
        " FROM audit_logs WHERE modulo='CAJA'"
    ).fetchall()


def test_each_canonical_event_writes_one_audit_row_with_uuid(bus):
    conn = make_db()
    register_cash_audit(bus, conn)
    branch, shift, cut, op = new_uuid(), new_uuid(), new_uuid(), new_uuid()

    bus.publish(EventName.CASH_SHIFT_OPENED.value, {
        "operation_id": op, "shift_id": shift, "branch_id": branch, "user": "ana",
    })
    bus.publish(EventName.CASH_Z_CUT_GENERATED.value, {
        "operation_id": new_uuid(), "shift_id": shift, "cut_id": cut,
        "branch_id": branch, "user": "ana",
    })

    rows = _audit_rows(conn)
    assert len(rows) == 2, "una fila por evento — ni cero (id faltante) ni duplicados"
    acciones = {r[1] for r in rows}
    assert acciones == {"TURNO_ABIERTO", "CORTE_Z"}
    for r in rows:
        assert r[0], "audit_logs.id debe acuñarse (UUIDv7)"
        assert r[4] == "ana" and r[5] == branch
    corte = next(r for r in rows if r[1] == "CORTE_Z")
    assert corte[3] == cut
    assert op in next(r for r in rows if r[1] == "TURNO_ABIERTO")[6]


def test_audit_subscribes_only_canonical_events(bus):
    register_cash_audit(bus, make_db())
    for evento in CASH_AUDIT_EVENTS:
        assert bus.handler_count(evento) == 1
    for legado in _LEGACY:
        assert bus.handler_count(legado) == 0


def test_audit_failure_is_logged_not_swallowed(bus, caplog):
    import sqlite3

    register_cash_audit(bus, sqlite3.connect(":memory:"))  # sin audit_logs
    with caplog.at_level("WARNING", logger="spj.events.cash_audit"):
        bus.publish(EventName.CASH_SHIFT_OPENED.value, {"shift_id": "x"})
    assert any("CashAuditHandler" in r.getMessage() for r in caplog.records)

# tests/unit/test_remediacion_a_cash_bridge.py
"""Remediación A — bridge canónico CAJA_* → CASH_* + audit de caja (DEEP_AUDIT B2).

Antes, los eventos de caja vivían en dos vocabularios paralelos (CAJA_* español,
CASH_* inglés) y ninguno tenía suscriptores. El bridge unifica ambos en el canal
canónico CASH_* y el audit handler deja trazabilidad.
"""
from __future__ import annotations

import sqlite3

import pytest

from core.events.event_bus import EventBus
from core.events.cash_event_bridge import (
    CASH_EVENT_MAP,
    CANONICAL_CASH_EVENTS,
    normalize_cash_payload,
    register_cash_event_bridge,
)
from backend.shared.events.event_names import EventName

LEGACY_EVENTS = tuple(CASH_EVENT_MAP.keys())


class _Container:
    def __init__(self, db):
        self.db = db


@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """CREATE TABLE audit_logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT, accion TEXT, modulo TEXT,
            entidad TEXT, entidad_id TEXT, usuario TEXT, sucursal_id TEXT,
            detalles TEXT, fecha TEXT)"""
    )
    yield conn
    conn.close()


@pytest.fixture()
def bus(db):
    b = EventBus()
    # Aislar canales de este test
    for evt in list(LEGACY_EVENTS) + list(CANONICAL_CASH_EVENTS):
        b.clear_handlers(evt)
    register_cash_event_bridge(b, _Container(db))
    yield b
    for evt in list(LEGACY_EVENTS) + list(CANONICAL_CASH_EVENTS):
        b.clear_handlers(evt)


def test_map_cubre_los_cuatro_eventos_de_caja():
    assert CASH_EVENT_MAP == {
        "CAJA_TURNO_ABIERTO": EventName.CASH_SHIFT_OPENED.value,
        "CAJA_MOVIMIENTO": EventName.CASH_MOVEMENT_RECORDED.value,
        "CAJA_CORTE_Z_GENERADO": EventName.CASH_Z_CUT_GENERATED.value,
        "CAJA_DIFERENCIA_DETECTADA": EventName.CASH_DIFFERENCE_DETECTED.value,
    }


def test_normalize_agrega_claves_inglesas_sin_perder_originales():
    out = normalize_cash_payload("CAJA_MOVIMIENTO", {
        "turno_id": "T1", "sucursal_id": "B1", "usuario": "ana",
        "tipo": "INGRESO", "monto": 50.0, "concepto": "fondo",
    })
    assert out["shift_id"] == "T1" and out["turno_id"] == "T1"
    assert out["branch_id"] == "B1"
    assert out["user"] == "ana"
    assert out["movement_type"] == "INGRESO"
    assert out["amount"] == 50.0
    assert out["concept"] == "fondo"
    assert out["source_event"] == "CAJA_MOVIMIENTO"


def test_evento_legacy_reemite_canonico(bus):
    recibidos = []
    bus.subscribe(EventName.CASH_Z_CUT_GENERATED.value,
                  lambda p: recibidos.append(p), label="test.cash_z")

    bus.publish("CAJA_CORTE_Z_GENERADO", {
        "cierre_id": "C1", "turno_id": "T1", "sucursal_id": "B1",
        "usuario": "ana", "total_ventas": 1000.0, "diferencia": -5.0,
    })

    assert len(recibidos) == 1, "El bridge no re-emitió CASH_Z_CUT_GENERATED"
    p = recibidos[0]
    assert p["cut_id"] == "C1" and p["branch_id"] == "B1"
    assert p["difference"] == -5.0


def test_evento_canonico_directo_tambien_llega(bus):
    """Un servicio backend que publica CASH_* directo también dispara consumidores."""
    recibidos = []
    bus.subscribe(EventName.CASH_MOVEMENT_RECORDED.value,
                  lambda p: recibidos.append(p), label="test.cash_mov")
    bus.publish(EventName.CASH_MOVEMENT_RECORDED.value,
                {"shift_id": "T2", "branch_id": "B1", "amount": 20.0})
    assert len(recibidos) == 1


def test_no_hay_loop_bridge(bus):
    """El bridge escucha CAJA_* y emite CASH_*; no debe re-disparar CAJA_*."""
    caja_recibidos = []
    bus.subscribe("CAJA_CORTE_Z_GENERADO",
                  lambda p: caja_recibidos.append(p), label="test.caja_z_probe")
    bus.publish("CAJA_CORTE_Z_GENERADO", {"cierre_id": "C1", "sucursal_id": "B1"})
    # Solo el evento original — no un rebote
    assert len(caja_recibidos) == 1


def test_audit_handler_escribe_por_evento_de_caja(bus, db):
    bus.publish("CAJA_TURNO_ABIERTO", {
        "turno_id": "T9", "sucursal_id": "B1", "usuario": "ana", "fondo_inicial": 500.0,
    })
    rows = db.execute(
        "SELECT accion, modulo, entidad_id, sucursal_id FROM audit_logs"
    ).fetchall()
    assert rows, "El audit handler no escribió la apertura de turno"
    accion, modulo, entidad_id, branch = rows[0]
    assert modulo == "CAJA"
    assert accion == "TURNO_ABIERTO"
    assert entidad_id == "T9"
    assert branch == "B1"


def test_corte_z_genera_audit_con_cut_id(bus, db):
    bus.publish("CAJA_CORTE_Z_GENERADO", {
        "cierre_id": "C7", "turno_id": "T7", "sucursal_id": "B2",
        "usuario": "leo", "total_ventas": 800.0, "diferencia": 0.0,
    })
    row = db.execute(
        "SELECT accion, entidad_id FROM audit_logs WHERE accion='CORTE_Z'"
    ).fetchone()
    assert row is not None and row[1] == "C7"

"""FASE 4 (caja) — turno identity flows as str (forward-compatible UUIDv7).

turnos_caja.id is still INTEGER PRIMARY KEY pre-cut, so abrir_turno cannot yet
mint a UUID into it (SQLite rejects text in an INTEGER PK); the lastrowid-free,
UUID-native version is gated on migration 200 (turnos_caja.id -> TEXT). Until
then the turno identity is normalized to str at every boundary so the cash flow
is already UUID-ready: a str '5' matches the integer 5 via SQLite type affinity
in WHERE/JOIN, and once the cut flips ids to TEXT no caller changes.
"""

from __future__ import annotations

import sqlite3

import pytest

from core.services.enterprise.finance_service import FinanceService


@pytest.fixture
def svc():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE turnos_caja (
            id TEXT PRIMARY KEY, sucursal_id TEXT, usuario TEXT,
            cajero TEXT, fondo_inicial REAL DEFAULT 0, total_ventas REAL DEFAULT 0,
            efectivo_esperado REAL DEFAULT 0, efectivo_contado REAL DEFAULT 0,
            diferencia REAL DEFAULT 0, estado TEXT DEFAULT 'abierto',
            fecha_apertura DATETIME DEFAULT (datetime('now')), fecha_cierre DATETIME
        );
        CREATE TABLE movimientos_caja (
            id TEXT PRIMARY KEY, turno_id TEXT, sucursal_id INTEGER,
            tipo TEXT, monto REAL, concepto TEXT, usuario TEXT,
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, sucursal_id INTEGER, usuario TEXT,
            total REAL, estado TEXT DEFAULT 'completada', forma_pago TEXT DEFAULT 'Efectivo',
            fecha DATETIME DEFAULT (datetime('now'))
        );
        CREATE TABLE cierres_caja (
            id TEXT PRIMARY KEY, tipo TEXT, sucursal_id TEXT, usuario TEXT,
            turno TEXT, turno_id TEXT, fecha_apertura DATETIME,
            fecha_cierre DATETIME, total_ventas REAL, num_ventas INTEGER,
            total_efectivo REAL, total_tarjeta REAL, total_transferencia REAL,
            total_otros REAL, total_anulaciones REAL, num_anulaciones INTEGER,
            efectivo_contado REAL, fondo_inicial REAL, diferencia REAL,
            comentarios TEXT, estado TEXT
        );
        """
    )
    conn.commit()
    return FinanceService(conn)


def test_abrir_turno_returns_str(svc):
    tid = svc.abrir_turno(sucursal_id=1, usuario="ana", fondo_inicial=100.0)
    assert isinstance(tid, str)


def test_get_estado_turno_id_is_str(svc):
    svc.abrir_turno(sucursal_id=1, usuario="ana", fondo_inicial=100.0)
    estado = svc.get_estado_turno(1, "ana")
    assert estado is not None
    assert isinstance(estado["id"], str)


def test_movimiento_links_via_str_turno_id(svc):
    tid = svc.abrir_turno(sucursal_id=1, usuario="ana", fondo_inicial=100.0)
    assert isinstance(tid, str)
    svc.registrar_movimiento_manual(tid, 1, "ana", "INGRESO", 50.0, "extra")
    svc.registrar_movimiento_manual(tid, 1, "ana", "RETIRO", 20.0, "gasto")
    movs = svc.get_movimientos_turno(tid)  # str turno_id resolves to int rows (affinity)
    assert len(movs) == 2


def test_corte_z_with_str_turno_id(svc):
    tid = svc.abrir_turno(sucursal_id=1, usuario="ana", fondo_inicial=100.0)
    svc.registrar_movimiento_manual(tid, 1, "ana", "INGRESO", 30.0, "extra")
    corte = svc.generar_corte_z(tid, 1, "ana", efectivo_fisico=130.0)
    assert str(corte["turno_id"]) == str(tid)
    assert corte["otros_ingresos"] == 30.0
    # turno is closed
    assert svc.get_estado_turno(1, "ana") is None

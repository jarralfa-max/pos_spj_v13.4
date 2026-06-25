"""FASE 4 (cards) — CardBatchEngine is functional against the reconciled schema.

After migration 112 the engine's full lifecycle works (crear_lote → marcar_impreso
→ liberar_lote → asignar_tarjeta → bloquear → desbloquear → historial) and card /
tarjeta / cliente identities flow as str (UUIDv7-ready). The id columns are still
INTEGER PK pre-cut, so the lastrowid-free version is gated on migración 200; here
the str boundary works against integer ids via SQLite type affinity.
"""

from __future__ import annotations

import sqlite3

import pytest

from core.services.card_batch_engine import CardBatchEngine


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT, apellido TEXT);
        INSERT INTO clientes (id, nombre) VALUES (7, 'Ana');
        CREATE TABLE card_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT UNIQUE NOT NULL, nombre TEXT NOT NULL,
            codigo_inicio TEXT NOT NULL, codigo_fin TEXT NOT NULL, cantidad INTEGER DEFAULT 0,
            cantidad_libres INTEGER DEFAULT 0, cantidad_asignadas INTEGER DEFAULT 0,
            estado TEXT DEFAULT 'activo', notas TEXT, generado_por TEXT,
            fecha_creacion DATETIME DEFAULT (datetime('now')), fecha_cierre DATETIME
        );
        CREATE TABLE tarjetas_fidelidad (
            id INTEGER PRIMARY KEY AUTOINCREMENT, codigo_qr TEXT, numero TEXT, batch_id TEXT,
            estado TEXT NOT NULL DEFAULT 'disponible', activa INTEGER DEFAULT 1,
            id_cliente INTEGER, puntos_actuales INTEGER DEFAULT 0, nivel TEXT DEFAULT 'Bronce',
            es_pregenerada INTEGER DEFAULT 0, fecha_creacion DATETIME DEFAULT (datetime('now')),
            fecha_asignacion DATETIME, bloqueado_por TEXT, motivo_bloqueo TEXT
        );
        CREATE UNIQUE INDEX ux_tarjetas_fidelidad_numero ON tarjetas_fidelidad(numero);
        CREATE TABLE card_assignment_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tarjeta_id TEXT NOT NULL, cliente_id_prev TEXT,
            cliente_id_nuevo TEXT, accion TEXT NOT NULL, motivo TEXT, usuario TEXT,
            fecha DATETIME DEFAULT (datetime('now'))
        );
        """
    )
    c.commit()
    return c


def test_crear_lote_returns_str_id_and_generates_cards(conn):
    eng = CardBatchEngine(conn, usuario="admin")
    batch = eng.crear_lote("Lote Test", prefijo="J", cantidad=5)
    assert isinstance(batch.id, str)            # identidad UUIDv7-ready
    assert batch.cantidad == 5
    n = conn.execute(
        "SELECT COUNT(*) FROM tarjetas_fidelidad WHERE batch_id=?", (batch.id,)
    ).fetchone()[0]
    assert n == 5


def test_full_lifecycle_assign_and_block(conn):
    eng = CardBatchEngine(conn, usuario="admin")
    batch = eng.crear_lote("Lote", prefijo="J", cantidad=3)
    assert eng.marcar_impreso(batch.id) == 3
    assert eng.liberar_lote(batch.id) == 3

    libres = eng.tarjetas_libres(batch_id=batch.id)
    assert len(libres) == 3
    tid = libres[0].id
    assert isinstance(tid, str)

    r = eng.asignar_tarjeta(tid, "7")
    assert r.exito, r.mensaje
    # counters synced on the batch
    assert eng._load_batch(batch.id).cantidad_asignadas == 1

    rb = eng.bloquear_tarjeta(tid, motivo="Extraviada")
    assert rb.exito, rb.mensaje

    hist = eng.historial_tarjeta(tid)
    acciones = {h["accion"] for h in hist}
    assert {"asignacion", "bloqueo"} <= acciones


def test_assignment_history_uses_str_identities(conn):
    eng = CardBatchEngine(conn, usuario="admin")
    batch = eng.crear_lote("Lote", prefijo="J", cantidad=1)
    eng.liberar_lote(batch.id)
    tid = eng.tarjetas_libres(batch_id=batch.id)[0].id
    eng.asignar_tarjeta(tid, "7")
    row = conn.execute(
        "SELECT tarjeta_id, cliente_id_nuevo FROM card_assignment_history LIMIT 1"
    ).fetchone()
    assert isinstance(row["tarjeta_id"], str)
    assert isinstance(row["cliente_id_nuevo"], str)

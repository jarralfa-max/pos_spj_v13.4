"""Migration 112 adds the loyalty-card columns CardBatchEngine depends on."""

from __future__ import annotations

import importlib
import sqlite3

import pytest


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    # Pre-migration ("v13") schema: the real columns, WITHOUT the v14 additions.
    conn.executescript(
        """
        CREATE TABLE tarjetas_fidelidad (
            id INTEGER PRIMARY KEY, codigo_qr TEXT NOT NULL, id_cliente INTEGER,
            estado TEXT NOT NULL DEFAULT 'disponible', puntos_iniciales INTEGER DEFAULT 0,
            puntos_actuales INTEGER DEFAULT 0, es_pregenerada INTEGER DEFAULT 0,
            nivel TEXT DEFAULT 'Bronce', fecha_creacion DATETIME DEFAULT (datetime('now')),
            fecha_asignacion DATETIME, bloqueado_por TEXT, motivo_bloqueo TEXT
        );
        CREATE TABLE card_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT, uuid TEXT UNIQUE NOT NULL, nombre TEXT NOT NULL,
            codigo_inicio TEXT NOT NULL, codigo_fin TEXT NOT NULL, cantidad INTEGER DEFAULT 0,
            cantidad_libres INTEGER DEFAULT 0, cantidad_asignadas INTEGER DEFAULT 0,
            estado TEXT DEFAULT 'activo', notas TEXT, fecha_creacion DATETIME DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()
    return conn


def _run(conn):
    mod = importlib.import_module("migrations.standalone.112_card_schema_reconciliation")
    mod.run(conn)


def test_migration_adds_missing_columns(db):
    _run(db)
    tf = _cols(db, "tarjetas_fidelidad")
    assert {"numero", "batch_id", "activa"} <= tf
    cb = _cols(db, "card_batches")
    assert {"generado_por", "fecha_cierre"} <= cb


def test_numero_unique_index_enforced(db):
    _run(db)
    db.execute("INSERT INTO tarjetas_fidelidad (id, codigo_qr, numero) VALUES (1,'q1','SPJ26000001')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO tarjetas_fidelidad (id, codigo_qr, numero) VALUES (2,'q2','SPJ26000001')")


def test_migration_is_idempotent(db):
    _run(db)
    _run(db)  # second run must not raise
    assert {"numero", "batch_id", "activa"} <= _cols(db, "tarjetas_fidelidad")


def test_legacy_rows_with_null_numero_do_not_conflict(db):
    _run(db)
    db.execute("INSERT INTO tarjetas_fidelidad (id, codigo_qr) VALUES (1,'q1')")
    db.execute("INSERT INTO tarjetas_fidelidad (id, codigo_qr) VALUES (2,'q2')")  # both NULL numero
    assert db.execute("SELECT COUNT(*) FROM tarjetas_fidelidad").fetchone()[0] == 2

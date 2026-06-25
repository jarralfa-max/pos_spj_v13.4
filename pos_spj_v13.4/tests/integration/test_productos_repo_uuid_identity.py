"""FASE 7 (productos) — legacy ProductoRepository.create is UUIDv7-native.

REGLA CERO: productos identity must be a UUIDv7 minted with new_uuid(), never
AUTOINCREMENT + lastrowid. Post-cut TEXT-id schema.
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from repositories.productos import ProductoRepository


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE productos (
            id TEXT PRIMARY KEY, nombre TEXT, nombre_normalizado TEXT, precio REAL DEFAULT 0,
            existencia REAL DEFAULT 0, stock_minimo REAL DEFAULT 0, unidad TEXT DEFAULT 'kg',
            categoria TEXT, oculto INTEGER DEFAULT 0, es_compuesto INTEGER DEFAULT 0,
            es_subproducto INTEGER DEFAULT 0, producto_padre_id TEXT, imagen_path TEXT,
            is_active INTEGER DEFAULT 1, deleted_at TEXT
        );
        CREATE TABLE logs (id TEXT PRIMARY KEY, modulo TEXT, accion TEXT, detalles TEXT, usuario TEXT);
        """
    )
    conn.commit()
    return conn


def test_create_returns_uuid_and_persists_uuid_id(db):
    new_id = ProductoRepository(db).create({"nombre": "Pollo", "precio": 50}, "qa")
    assert isinstance(new_id, str)
    assert uuid.UUID(new_id)  # UUIDv7 string, not a rowid int
    row = db.execute("SELECT id FROM productos").fetchone()
    assert row["id"] == new_id


def test_audit_log_row_has_uuid_id(db):
    ProductoRepository(db).create({"nombre": "Res", "precio": 80}, "qa")
    log = db.execute("SELECT id FROM logs").fetchone()
    assert log is not None and uuid.UUID(log["id"])

"""Tests for the atomic UUIDv7 cutover engine (FASE 2.5 machinery).

Exercise the engine on a controlled synthetic schema with parent/child/self-ref
relationships: PK + FK rewriting, count validation, orphan handling, atomic
rollback, and UUIDv7 validity.
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest

from backend.infrastructure.db.uuid_cutover import (
    TableSpec,
    UuidCutover,
    UuidCutoverError,
)


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE sucursales (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT NOT NULL);
        CREATE TABLE productos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, precio REAL DEFAULT 0);
        CREATE TABLE ventas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, folio TEXT, sucursal_id INTEGER, total REAL
        );
        CREATE TABLE detalles_venta (
            id INTEGER PRIMARY KEY AUTOINCREMENT, venta_id INTEGER, producto_id INTEGER, cantidad REAL
        );
        -- self-referential parent_id
        CREATE TABLE contenedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT, codigo TEXT, parent_id INTEGER
        );

        INSERT INTO sucursales (id, nombre) VALUES (1,'Centro'),(2,'Norte');
        INSERT INTO productos (id, nombre, precio) VALUES (10,'Pechuga',95.0),(11,'Pierna',75.0);
        INSERT INTO ventas (id, folio, sucursal_id, total) VALUES (100,'V-1',1,190.0),(101,'V-2',2,75.0);
        INSERT INTO detalles_venta (id, venta_id, producto_id, cantidad) VALUES
            (1000,100,10,2.0),(1001,100,11,1.0),(1002,101,11,1.0);
        INSERT INTO contenedores (id, codigo, parent_id) VALUES (5,'C-A',NULL),(6,'C-B',5);
        """
    )
    conn.commit()
    return conn


SPECS = [
    TableSpec("sucursales"),
    TableSpec("productos"),
    TableSpec("ventas", fks={"sucursal_id": "sucursales"}),
    TableSpec("detalles_venta", fks={"venta_id": "ventas", "producto_id": "productos"}),
    TableSpec("contenedores", fks={"parent_id": "contenedores"}),
]


def _is_uuid7(value) -> bool:
    parsed = uuid.UUID(str(value))
    return parsed.version == 7 and str(parsed) == str(value).lower()


def test_cutover_converts_pk_and_fks_to_uuid():
    conn = _db()
    counts = UuidCutover(conn, SPECS).run()
    assert counts == {"sucursales": 2, "productos": 2, "ventas": 2,
                      "detalles_venta": 3, "contenedores": 2}

    # every PK is a UUIDv7
    for table in ("sucursales", "productos", "ventas", "detalles_venta", "contenedores"):
        for r in conn.execute(f"SELECT id FROM {table}"):
            assert _is_uuid7(r["id"])

    # FK relationships are preserved through the remap
    v1 = conn.execute("SELECT id FROM ventas WHERE folio='V-1'").fetchone()["id"]
    suc_centro = conn.execute("SELECT id FROM sucursales WHERE nombre='Centro'").fetchone()["id"]
    assert conn.execute("SELECT sucursal_id FROM ventas WHERE folio='V-1'").fetchone()[0] == suc_centro
    # V-1 has two detail lines, both now pointing at V-1's uuid
    det = conn.execute("SELECT COUNT(*) FROM detalles_venta WHERE venta_id=?", (v1,)).fetchone()[0]
    assert det == 2


def test_self_referential_fk_is_remapped():
    conn = _db()
    UuidCutover(conn, SPECS).run()
    parent = conn.execute("SELECT id FROM contenedores WHERE codigo='C-A'").fetchone()["id"]
    child = conn.execute("SELECT parent_id FROM contenedores WHERE codigo='C-B'").fetchone()["parent_id"]
    assert child == parent and _is_uuid7(parent)
    # the root container keeps a NULL parent
    root = conn.execute("SELECT parent_id FROM contenedores WHERE codigo='C-A'").fetchone()["parent_id"]
    assert root is None


def test_schema_has_no_integer_autoincrement_after_cutover():
    conn = _db()
    UuidCutover(conn, SPECS).run()
    for table in ("ventas", "detalles_venta", "productos"):
        ddl = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()[0].upper()
        assert "AUTOINCREMENT" not in ddl
        assert '"ID" TEXT PRIMARY KEY' in ddl or "ID TEXT PRIMARY KEY" in ddl


def test_orphan_fk_aborts_and_rolls_back():
    conn = _db()
    # point a detail line at a non-existent venta
    conn.execute("INSERT INTO detalles_venta (id, venta_id, producto_id, cantidad) VALUES (9999, 555, 10, 1.0)")
    conn.commit()
    with pytest.raises(UuidCutoverError, match="orphan FK"):
        UuidCutover(conn, SPECS).run()
    # rolled back: original integer schema intact, no leftover __uuid_new tables
    assert conn.execute("SELECT id FROM ventas WHERE folio='V-1'").fetchone()["id"] == 100
    leftovers = conn.execute(
        "SELECT name FROM sqlite_master WHERE name LIKE '%__uuid_new'"
    ).fetchall()
    assert leftovers == []


def test_orphan_fk_nulled_when_configured():
    conn = _db()
    conn.execute("INSERT INTO detalles_venta (id, venta_id, producto_id, cantidad) VALUES (9999, 555, 10, 1.0)")
    conn.commit()
    UuidCutover(conn, SPECS, on_orphan="null").run()
    row = conn.execute("SELECT venta_id, producto_id FROM detalles_venta WHERE cantidad=1.0 AND producto_id IS NOT NULL").fetchall()
    orphan = conn.execute("SELECT venta_id FROM detalles_venta WHERE id IS NOT NULL AND venta_id IS NULL").fetchall()
    assert len(orphan) == 1  # the orphan's venta_id was nulled


def test_count_preserved_for_every_table():
    conn = _db()
    before = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("sucursales", "productos", "ventas", "detalles_venta", "contenedores")}
    UuidCutover(conn, SPECS).run()
    after = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
             for t in before}
    assert before == after


def test_non_id_columns_and_defaults_preserved():
    conn = _db()
    UuidCutover(conn, SPECS).run()
    row = conn.execute("SELECT nombre, precio FROM productos WHERE nombre='Pechuga'").fetchone()
    assert (row["nombre"], row["precio"]) == ("Pechuga", 95.0)
    # default preserved in DDL
    ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name='productos'").fetchone()[0]
    assert "DEFAULT 0" in ddl


def test_idempotent_uuids_are_unique():
    conn = _db()
    UuidCutover(conn, SPECS).run()
    ids = [r[0] for r in conn.execute("SELECT id FROM detalles_venta")]
    assert len(ids) == len(set(ids))

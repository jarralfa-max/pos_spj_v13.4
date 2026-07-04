"""Robustness fixes for the UuidCutover engine, found by running the cut against
the real bootstrapped schema.

These three classes of bug would crash or corrupt a real cutover:
  1. Expression defaults (``DEFAULT (datetime('now'))``) — PRAGMA strips the
     wrapping parens, so a naive re-emit is a syntax error.
  2. Sentinel FK values (0 / '') — legacy "no reference"; an INTEGER PK never
     yields 0, so these must become NULL, not abort the cut as orphans.
  3. Type-mismatched FK resolution — a TEXT FK '1' (forward-compatible str
     identity columns) must resolve to an INTEGER parent PK 1.
"""

from __future__ import annotations

import sqlite3
import uuid

from backend.infrastructure.db.uuid_cutover import TableSpec, UuidCutover


def _is_uuid7(v):
    return uuid.UUID(str(v)).version == 7


def test_expression_default_is_reparenthesized():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "created_at DATETIME DEFAULT (datetime('now')), nombre TEXT DEFAULT 'x')"
    )
    conn.execute("INSERT INTO t (nombre) VALUES ('a')")
    conn.commit()
    UuidCutover(conn, [TableSpec("t")]).run()
    # default still works on the rewritten table
    conn.execute("INSERT INTO t (id, nombre) VALUES ('z', 'b')")
    row = conn.execute("SELECT created_at FROM t WHERE id='z'").fetchone()
    assert row[0] is not None  # DEFAULT (datetime('now')) survived the rewrite


def test_zero_sentinel_fk_becomes_null_not_orphan():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE sucursales (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT);
        CREATE TABLE reglas (id INTEGER PRIMARY KEY AUTOINCREMENT, sucursal_id INTEGER);
        INSERT INTO sucursales (id, nombre) VALUES (1, 'Centro');
        INSERT INTO reglas (id, sucursal_id) VALUES (1, 0), (2, 1);
        """
    )
    conn.commit()
    specs = [TableSpec("sucursales"), TableSpec("reglas", fks={"sucursal_id": "sucursales"})]
    UuidCutover(conn, specs).run()  # must not raise on the sentinel 0
    rows = {r[0]: r[1] for r in conn.execute("SELECT nombre, sucursal_id FROM reglas r "
            "LEFT JOIN sucursales s ON s.id=r.sucursal_id").fetchall()}
    sentinel = conn.execute(
        "SELECT sucursal_id FROM reglas WHERE id IN (SELECT id FROM reglas) AND sucursal_id IS NULL"
    ).fetchall()
    assert len(sentinel) == 1  # the 0-sentinel row was nulled
    # the real reference was remapped to a UUID
    real = conn.execute("SELECT sucursal_id FROM reglas WHERE sucursal_id IS NOT NULL").fetchone()
    assert _is_uuid7(real[0])
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_text_fk_resolves_to_integer_parent_pk():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE card_batches (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT);
        CREATE TABLE tarjetas (id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT);
        INSERT INTO card_batches (id, nombre) VALUES (1, 'L1');
        INSERT INTO tarjetas (id, batch_id) VALUES (1, '1');  -- TEXT '1' -> INTEGER 1
        """
    )
    conn.commit()
    specs = [TableSpec("card_batches"), TableSpec("tarjetas", fks={"batch_id": "card_batches"})]
    UuidCutover(conn, specs).run()
    batch_pk = conn.execute("SELECT id FROM card_batches").fetchone()[0]
    fk = conn.execute("SELECT batch_id FROM tarjetas").fetchone()[0]
    assert _is_uuid7(fk)
    assert fk == batch_pk  # the TEXT '1' resolved to the integer parent's new UUID
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

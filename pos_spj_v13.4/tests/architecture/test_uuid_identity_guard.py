"""REGLA CERO paso 13 — startup guard that blocks an un-cut (INTEGER PK) DB.

The runtime assumes the post-cut UUIDv7 schema, so the app must refuse to start
(with the cutover runbook) rather than fail later with a cryptic datatype error.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.db.uuid_cutover import (
    IntegerIdentityError,
    TableSpec,
    UuidCutover,
    assert_uuid_identity,
    find_integer_pks,
)


def _uncut():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE schema_migrations (id INTEGER PRIMARY KEY, version TEXT);
        CREATE TABLE sucursales (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT);
        CREATE TABLE ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, sucursal_id INTEGER);
        INSERT INTO sucursales (id, nombre) VALUES (1, 'Centro');
        INSERT INTO ventas (id, sucursal_id) VALUES (1, 1);
        """
    )
    conn.commit()
    return conn


def test_find_integer_pks_flags_domain_tables_only():
    conn = _uncut()
    bad = find_integer_pks(conn)
    assert "ventas" in bad and "sucursales" in bad
    assert "schema_migrations" not in bad  # migration infra is excluded


def test_assert_uuid_identity_raises_on_uncut_db():
    conn = _uncut()
    with pytest.raises(IntegerIdentityError) as exc:
        assert_uuid_identity(conn)
    msg = str(exc.value)
    assert "200" in msg and "SPJ_UUID_CUTOVER_CONFIRMED=1" in msg  # actionable runbook


def test_assert_uuid_identity_passes_after_cut():
    conn = _uncut()
    UuidCutover(conn, [TableSpec("sucursales"),
                       TableSpec("ventas", fks={"sucursal_id": "sucursales"})]).run()
    # schema_migrations keeps its integer id but is infra → still passes
    assert find_integer_pks(conn) == {}
    assert_uuid_identity(conn)  # must not raise


def test_assert_uuid_identity_passes_on_text_id_schema():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE clientes (id TEXT PRIMARY KEY, nombre TEXT)")
    conn.commit()
    assert_uuid_identity(conn)  # no integer PK → no raise

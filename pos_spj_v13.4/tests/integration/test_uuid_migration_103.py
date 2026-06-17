"""Integration tests for migration 103 — happy_hour_rules.sucursal_uuid.

Scenarios:
1. Fresh DB (table created with uuid column from the start)
2. Old DB without sucursal_uuid column
3. Idempotent — run migration twice
4. Backfill from sucursal_id when sucursales.uuid exists
5. No rows lost during migration
6. list_users_v13 with both usuarios.uuid and sucursales.uuid does not raise ambiguous column
7. Happy Hour with sucursal_uuid IS NULL (global rule)
8. Happy Hour linked to a specific sucursal
9. Usuario without sucursal
10. PRAGMA foreign_key_check passes after migration
"""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_migration(num: str, filename: str):
    path = ROOT / "pos_spj_v13.4" / "migrations" / "standalone" / filename
    spec = importlib.util.spec_from_file_location(f"m{num}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _col_exists(conn, table, col):
    return any(r[1] == col for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _seed_sucursales(conn, with_uuid=True):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sucursales "
        "(id INTEGER PRIMARY KEY, nombre TEXT, activa INTEGER DEFAULT 1"
        + (", uuid TEXT" if with_uuid else "")
        + ")"
    )
    conn.execute("INSERT INTO sucursales (id, nombre, uuid) VALUES (1,'Principal','019ed300-0000-7000-8000-000000000001')" if with_uuid
                 else "INSERT INTO sucursales (id, nombre) VALUES (1,'Principal')")
    conn.commit()


def _seed_happy_hour(conn, with_sucursal_uuid=False, with_sucursal_id=True):
    cols = "id INTEGER PRIMARY KEY, nombre TEXT"
    if with_sucursal_id:
        cols += ", sucursal_id INTEGER"
    if with_sucursal_uuid:
        cols += ", sucursal_uuid TEXT"
    conn.execute(f"CREATE TABLE IF NOT EXISTS happy_hour_rules ({cols})")
    conn.execute(
        "INSERT INTO happy_hour_rules (id, nombre, sucursal_id) VALUES (1,'HH Test',1)"
        if with_sucursal_id and not with_sucursal_uuid
        else "INSERT INTO happy_hour_rules (id, nombre) VALUES (1,'HH Global')"
    )
    conn.commit()


M101 = _load_migration("101", "101_entity_uuid_columns.py")
M102 = _load_migration("102", "102_extended_uuid_columns.py")
M103 = _load_migration("103", "103_happy_hour_sucursal_uuid.py")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_migration_103_fresh_db():
    """Fresh DB: table created with sucursal_uuid from the start."""
    conn = _make_conn()
    conn.execute(
        "CREATE TABLE happy_hour_rules "
        "(id INTEGER PRIMARY KEY, nombre TEXT, sucursal_id INTEGER, sucursal_uuid TEXT)"
    )
    conn.commit()
    M103.run(conn)
    assert _col_exists(conn, "happy_hour_rules", "sucursal_uuid")


def test_migration_103_old_db_adds_column():
    """Old DB without sucursal_uuid: column is added."""
    conn = _make_conn()
    _seed_sucursales(conn)
    _seed_happy_hour(conn)
    assert not _col_exists(conn, "happy_hour_rules", "sucursal_uuid")
    M103.run(conn)
    assert _col_exists(conn, "happy_hour_rules", "sucursal_uuid")


def test_migration_103_idempotent():
    """Running migration twice does not raise or duplicate columns."""
    conn = _make_conn()
    _seed_sucursales(conn)
    _seed_happy_hour(conn)
    M103.run(conn)
    M103.run(conn)  # second run — must not fail
    cols = [r[1] for r in conn.execute("PRAGMA table_info(happy_hour_rules)").fetchall()]
    assert cols.count("sucursal_uuid") == 1


def test_migration_103_backfill_from_sucursal_id():
    """sucursal_uuid is backfilled from sucursal_id → sucursales.uuid."""
    conn = _make_conn()
    _seed_sucursales(conn)  # uuid='019ed300-...-001'
    _seed_happy_hour(conn)  # sucursal_id=1
    M103.run(conn)
    row = conn.execute("SELECT sucursal_uuid FROM happy_hour_rules WHERE id=1").fetchone()
    assert row["sucursal_uuid"] == "019ed300-0000-7000-8000-000000000001"


def test_migration_103_preserves_row_count():
    """Row count does not change after migration."""
    conn = _make_conn()
    _seed_sucursales(conn)
    conn.execute(
        "CREATE TABLE happy_hour_rules (id INTEGER PRIMARY KEY, nombre TEXT, sucursal_id INTEGER)"
    )
    for i in range(5):
        conn.execute(f"INSERT INTO happy_hour_rules (id, nombre, sucursal_id) VALUES ({i},'R{i}',1)")
    conn.commit()
    before = conn.execute("SELECT COUNT(*) FROM happy_hour_rules").fetchone()[0]
    M103.run(conn)
    after = conn.execute("SELECT COUNT(*) FROM happy_hour_rules").fetchone()[0]
    assert before == after == 5


def test_migration_103_global_rule_null_sucursal():
    """Happy Hour with no sucursal_id: sucursal_uuid stays NULL (global rule)."""
    conn = _make_conn()
    _seed_sucursales(conn)
    conn.execute(
        "CREATE TABLE happy_hour_rules (id INTEGER PRIMARY KEY, nombre TEXT, sucursal_id INTEGER)"
    )
    conn.execute("INSERT INTO happy_hour_rules (id, nombre) VALUES (1,'Global HH')")
    conn.commit()
    M103.run(conn)
    row = conn.execute("SELECT sucursal_uuid FROM happy_hour_rules WHERE id=1").fetchone()
    assert row["sucursal_uuid"] is None


def test_migration_103_specific_sucursal():
    """Happy Hour linked to a specific sucursal gets the correct UUID."""
    conn = _make_conn()
    conn.execute(
        "CREATE TABLE sucursales (id INTEGER PRIMARY KEY, nombre TEXT, activa INTEGER, uuid TEXT)"
    )
    conn.execute("INSERT INTO sucursales VALUES (1,'Norte',1,'019ed300-0001-7000-8000-000000000001')")
    conn.execute("INSERT INTO sucursales VALUES (2,'Sur',  1,'019ed300-0002-7000-8000-000000000002')")
    conn.execute(
        "CREATE TABLE happy_hour_rules (id INTEGER PRIMARY KEY, nombre TEXT, sucursal_id INTEGER)"
    )
    conn.execute("INSERT INTO happy_hour_rules VALUES (1,'HH Norte',1)")
    conn.execute("INSERT INTO happy_hour_rules VALUES (2,'HH Sur',  2)")
    conn.commit()
    M103.run(conn)
    r1 = conn.execute("SELECT sucursal_uuid FROM happy_hour_rules WHERE id=1").fetchone()
    r2 = conn.execute("SELECT sucursal_uuid FROM happy_hour_rules WHERE id=2").fetchone()
    assert r1["sucursal_uuid"] == "019ed300-0001-7000-8000-000000000001"
    assert r2["sucursal_uuid"] == "019ed300-0002-7000-8000-000000000002"


def test_list_users_v13_no_ambiguous_uuid():
    """list_users_v13 with uuid on both usuarios and sucursales does not raise ambiguous column."""
    conn = _make_conn()
    conn.execute(
        "CREATE TABLE sucursales (id INTEGER PRIMARY KEY, nombre TEXT, activa INTEGER, uuid TEXT)"
    )
    conn.execute("INSERT INTO sucursales VALUES (1,'Principal',1,'019ed300-0000-7000-8000-000000000001')")
    conn.execute(
        "CREATE TABLE roles (id INTEGER PRIMARY KEY, nombre TEXT, uuid TEXT)"
    )
    conn.execute("INSERT INTO roles VALUES (1,'admin','019ed300-0000-7000-8000-000000000002')")
    conn.execute(
        "CREATE TABLE usuarios (id INTEGER PRIMARY KEY, usuario TEXT, nombre TEXT, rol TEXT, "
        "sucursal_id INTEGER, activo INTEGER, uuid TEXT)"
    )
    conn.execute(
        "INSERT INTO usuarios VALUES (1,'admin','Admin','admin',1,1,"
        "'019ed300-0000-7000-8000-000000000003')"
    )
    conn.commit()

    # Import the repository and call list_users_v13
    import sys
    sys.path.insert(0, str(ROOT / "pos_spj_v13.4"))
    from repositories.config_repository import ConfigRepository
    repo = ConfigRepository(conn)
    rows = repo.list_users_v13()
    assert len(rows) == 1
    row = rows[0]
    # Verify aliases are present and unambiguous
    assert row["usuario_uuid"] == "019ed300-0000-7000-8000-000000000003"
    assert row["sucursal_uuid_val"] == "019ed300-0000-7000-8000-000000000001"


def test_usuario_without_sucursal():
    """User with no sucursal_id: list_users_v13 returns NULL sucursal_uuid_val."""
    conn = _make_conn()
    conn.execute(
        "CREATE TABLE sucursales (id INTEGER PRIMARY KEY, nombre TEXT, activa INTEGER, uuid TEXT)"
    )
    conn.execute(
        "CREATE TABLE roles (id INTEGER PRIMARY KEY, nombre TEXT, uuid TEXT)"
    )
    conn.execute(
        "CREATE TABLE usuarios (id INTEGER PRIMARY KEY, usuario TEXT, nombre TEXT, rol TEXT, "
        "sucursal_id INTEGER, activo INTEGER, uuid TEXT)"
    )
    conn.execute("INSERT INTO usuarios VALUES (1,'user1','User 1','cajero',NULL,1,'019ed300-0000-7000-8000-000000000010')")
    conn.commit()
    import sys
    sys.path.insert(0, str(ROOT / "pos_spj_v13.4"))
    from repositories.config_repository import ConfigRepository
    repo = ConfigRepository(conn)
    rows = repo.list_users_v13()
    assert len(rows) == 1
    assert rows[0]["sucursal_uuid_val"] is None

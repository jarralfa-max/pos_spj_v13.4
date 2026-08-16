"""CRM-25 regression: `create_cliente_minimo`'s dev-only SQLite fallback
must assign a real UUIDv7 `clientes.id` — previously it omitted `id`
entirely and returned `cursor.lastrowid` (the hidden ROWID, not the real
TEXT primary key), silently inserting a row with a NULL id."""
import sys
from pathlib import Path
import sqlite3

# Order matters: whatsapp_service's own `config/` package (a real package
# with a `settings` submodule) must resolve before the ERP's unrelated
# top-level `config.py` (a single file, `pos_spj_v13.4/pos_spj_v13.4/config.py`)
# — the same name collides across the two codebases sharing one process.
# `sys.path.insert(0, X)` always wins over an earlier insert(0, ...), so the
# ERP path must be inserted FIRST here, whatsapp_service's own path SECOND.
# (Pre-existing sibling test files insert these in the opposite order and
# fail to collect for the same reason — a known, unrelated gap, not
# something this CRM-25 phase fixes repo-wide.)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pos_spj_v13.4"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from erp.bridge import ERPBridge


def _db_path(tmp_path):
    dbp = tmp_path / "erp.db"
    conn = sqlite3.connect(dbp)
    conn.execute(
        "CREATE TABLE clientes (id TEXT PRIMARY KEY, nombre TEXT, telefono TEXT, activo INTEGER DEFAULT 1)"
    )
    conn.commit()
    conn.close()
    return str(dbp)


def test_create_cliente_minimo_assigns_real_uuid_id(tmp_path):
    bridge = ERPBridge(_db_path(tmp_path))
    assert not bridge._use_api  # no ERP_API_URL/KEY configured -> SQLite fallback

    cliente_id = bridge.create_cliente_minimo("Juan Nuevo", "5551112222")

    assert isinstance(cliente_id, str)
    assert cliente_id, "cliente_id must not be empty/None"
    row = bridge.db.execute(
        "SELECT id, nombre, telefono FROM clientes WHERE id=?", (cliente_id,)
    ).fetchone()
    assert row is not None, "inserted row must be findable by its returned id"
    assert row["nombre"] == "Juan Nuevo"
    assert row["telefono"] == "5551112222"


def test_create_cliente_minimo_ids_are_unique_across_calls(tmp_path):
    bridge = ERPBridge(_db_path(tmp_path))

    id_a = bridge.create_cliente_minimo("Cliente A", "5550001111")
    id_b = bridge.create_cliente_minimo("Cliente B", "5550002222")

    assert id_a != id_b
    count = bridge.db.execute("SELECT COUNT(*) FROM clientes").fetchone()[0]
    assert count == 2

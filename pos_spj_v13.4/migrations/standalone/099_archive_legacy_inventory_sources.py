"""Archive legacy inventory tables after canonical inventory adoption.

FASE 7: inventory_stock / inventory_movements are the canonical operational
source. The old tables are renamed to legacy_* when present so new runtime code
cannot keep using them as an operational path.
"""
from __future__ import annotations

import sqlite3

LEGACY_INVENTORY_TABLES = {
    "inventario_actual": "legacy_inventario_actual",
    "branch_inventory": "legacy_branch_inventory",
    "movimientos_inventario": "legacy_movimientos_inventario",
}


def _relation_type(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute(
        "SELECT type FROM sqlite_master WHERE name = ? AND type IN ('table', 'view') LIMIT 1",
        (name,),
    ).fetchone()
    return None if row is None else str(row[0])


def _archive_table(conn: sqlite3.Connection, source: str, archived: str) -> None:
    source_type = _relation_type(conn, source)
    if source_type is None:
        return

    if source_type == "view":
        conn.execute(f"DROP VIEW IF EXISTS {source}")
        return

    archived_type = _relation_type(conn, archived)
    if archived_type is None:
        conn.execute(f"ALTER TABLE {source} RENAME TO {archived}")
        return

    # Development database: the canonical route is more important than keeping a
    # duplicated legacy operational path. If an archive already exists, remove
    # the re-created legacy source so operational code cannot keep writing it.
    conn.execute(f"DROP TABLE IF EXISTS {source}")


def run(conn: sqlite3.Connection) -> None:
    for source, archived in LEGACY_INVENTORY_TABLES.items():
        _archive_table(conn, source, archived)
    conn.commit()


up = run

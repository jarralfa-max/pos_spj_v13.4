"""Archive legacy inventory tables after canonical inventory adoption.

FASE 7: inventory_stock / inventory_movements are the canonical operational
source. The old tables are renamed to legacy_* when present so new runtime code
cannot keep using them as an operational path.
"""
from __future__ import annotations

import sqlite3

NEGATIVE_INVENTORY_VIEW = "v_negative_inventory"

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


def _drop_legacy_negative_inventory_view(conn: sqlite3.Connection) -> None:
    """Remove the legacy view before table archival.

    SQLite validates dependent views while renaming tables. Production databases
    may contain a stale v_negative_inventory view pointing at the transient
    branch_inventory_old table left by previous ALTER TABLE operations. Dropping
    it first makes the migration safe even when that legacy table no longer
    exists.
    """

    conn.execute(f"DROP VIEW IF EXISTS {NEGATIVE_INVENTORY_VIEW}")


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return _relation_type(conn, name) == "table"


def _recreate_negative_inventory_view(conn: sqlite3.Connection) -> None:
    if not _has_table(conn, "inventory_stock"):
        return
    conn.execute(
        f"""
        CREATE VIEW IF NOT EXISTS {NEGATIVE_INVENTORY_VIEW} AS
        SELECT product_id, branch_id, quantity
        FROM inventory_stock
        WHERE quantity < 0
        """
    )


def run(conn: sqlite3.Connection) -> None:
    _drop_legacy_negative_inventory_view(conn)
    legacy_alter_row = conn.execute("PRAGMA legacy_alter_table").fetchone()
    previous_legacy_alter = int((legacy_alter_row[0] if legacy_alter_row else 0) or 0)
    conn.execute("PRAGMA legacy_alter_table=ON")
    try:
        for source, archived in LEGACY_INVENTORY_TABLES.items():
            _archive_table(conn, source, archived)
    finally:
        conn.execute(f"PRAGMA legacy_alter_table={previous_legacy_alter}")
    _recreate_negative_inventory_view(conn)
    conn.commit()


up = run

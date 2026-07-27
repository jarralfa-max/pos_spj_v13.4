"""097_waste_schema_integrity.py — canonical waste schema hardening.

Ensures the canonical MERMA route has the columns and indexes used by
WasteRepository/WasteApplicationService without creating schema from services/UI.
All operations are idempotent and safe for existing SQLite databases.
"""
from __future__ import annotations

import logging
import sqlite3

logger = logging.getLogger("spj.migrations.097")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})").fetchall())
    except Exception:
        return False


def _add_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if not _table_exists(conn, table) or _column_exists(conn, table, column):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    logger.info("097: added %s.%s", table, column)



def _create_index_if_columns_exist(
    conn: sqlite3.Connection,
    *,
    table: str,
    index_name: str,
    columns: tuple[str, ...],
    unique: bool = False,
    where: str = "",
) -> None:
    if not _table_exists(conn, table) or not all(_column_exists(conn, table, column) for column in columns):
        logger.warning("097: skipped index %s; missing table/columns", index_name)
        return
    unique_sql = "UNIQUE " if unique else ""
    where_sql = f" WHERE {where}" if where else ""
    conn.execute(
        f"CREATE {unique_sql}INDEX IF NOT EXISTS {index_name} "
        f"ON {table}({', '.join(columns)}){where_sql}"
    )

def _has_duplicate_operation_ids(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        """
        SELECT operation_id
        FROM mermas
        WHERE operation_id IS NOT NULL AND TRIM(operation_id) <> ''
        GROUP BY operation_id
        HAVING COUNT(*) > 1
        LIMIT 1
        """
    ).fetchone()
    return row is not None


def run(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "mermas"):
        logger.warning("097: mermas table does not exist; skipping waste schema hardening")
        return

    _add_column(conn, "mermas", "costo_unitario", "REAL DEFAULT 0")
    _add_column(conn, "mermas", "valor_perdida", "REAL DEFAULT 0")
    _add_column(conn, "mermas", "notas", "TEXT")
    _add_column(conn, "mermas", "fecha", "TEXT")

    _create_index_if_columns_exist(conn, table="mermas", index_name="idx_mermas_producto_id", columns=("producto_id",))
    _create_index_if_columns_exist(conn, table="mermas", index_name="idx_mermas_sucursal_id", columns=("sucursal_id",))
    _create_index_if_columns_exist(conn, table="mermas", index_name="idx_mermas_fecha", columns=("fecha",))
    _create_index_if_columns_exist(
        conn,
        table="mermas",
        index_name="idx_mermas_producto_sucursal_fecha",
        columns=("producto_id", "sucursal_id", "fecha"),
    )
    _create_index_if_columns_exist(conn, table="productos", index_name="idx_productos_nombre", columns=("nombre",))

    if _column_exists(conn, "mermas", "operation_id"):
        if _has_duplicate_operation_ids(conn):
            _create_index_if_columns_exist(
                conn, table="mermas", index_name="idx_mermas_operation_id", columns=("operation_id",)
            )
            logger.warning(
                "097: duplicate mermas.operation_id values found; created non-unique index only"
            )
        else:
            _create_index_if_columns_exist(
                conn,
                table="mermas",
                index_name="ux_mermas_operation_id",
                columns=("operation_id",),
                unique=True,
                where="operation_id IS NOT NULL AND TRIM(operation_id) <> ''",
            )

    conn.commit()


up = run

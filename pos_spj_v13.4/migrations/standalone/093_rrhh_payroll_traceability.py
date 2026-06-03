"""093_rrhh_payroll_traceability.py — RRHH payroll idempotency/traceability.

Adds nullable compatibility columns to legacy nomina_pagos so payroll payments can
be linked to canonical RRHH events without destructive schema changes.
"""
from __future__ import annotations

import sqlite3

DESCRIPTION = "RRHH payroll traceability: operation_id/source_module/source_id"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return bool(row)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_column(conn: sqlite3.Connection, table: str, definition: str) -> None:
    column = definition.split()[0]
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def run(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "nomina_pagos"):
        return

    _ensure_column(conn, "nomina_pagos", "operation_id TEXT")
    _ensure_column(conn, "nomina_pagos", "source_module TEXT DEFAULT 'rrhh'")
    _ensure_column(conn, "nomina_pagos", "source_id INTEGER")

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_nomina_pagos_operation_id "
        "ON nomina_pagos(operation_id) WHERE operation_id IS NOT NULL AND operation_id <> ''"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_nomina_pagos_source "
        "ON nomina_pagos(source_module, source_id)"
    )
    conn.commit()


up = run

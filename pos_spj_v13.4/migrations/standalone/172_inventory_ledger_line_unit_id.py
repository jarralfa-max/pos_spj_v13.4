# migrations/standalone/172_inventory_ledger_line_unit_id.py
"""P0-B (§4.3) — unidad canónica (`unit_id` UUIDv7) en líneas del ledger.

La columna `unit` de `inventory_ledger_lines` es un código de texto libre ("PZA",
"KG"). La identidad canónica de unidad es una referencia al catálogo de Productos
(`units_of_measure.id`, UUIDv7). Esta migración añade la columna `unit_id TEXT`
(nullable durante la transición) sin tocar `unit` (compat). Aditiva e idempotente:
sólo agrega la columna si aún no existe.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.172")


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(row[1] == column
               for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def run(conn) -> None:
    table = "inventory_ledger_lines"
    if not _table_exists(conn, table):
        logger.info("172: %s no existe todavía (esquema born-clean lo crea con "
                    "unit_id); nada que migrar", table)
        return
    if _column_exists(conn, table, "unit_id"):
        logger.info("172: %s.unit_id ya existe; idempotente", table)
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN unit_id TEXT")
    logger.info("172: %s.unit_id agregado (unidad canónica §4.3)", table)

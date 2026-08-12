# migrations/standalone/184_inventory_cold_chain_resolution.py
"""INV-9 (§21) — resolución operacional de excursiones de cadena de frío.

Agrega `inventory_temperature_excursions.resolved_by/resolved_at/resolution_note`
— quién resolvió la excursión, cuándo y por qué. Aditiva e idempotente, igual que
la 180 (capacidad de almacenes/ubicaciones).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.184")


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(row[1] == column
               for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _add_column(conn, table: str, column: str, ddl_type: str) -> None:
    if not _table_exists(conn, table):
        logger.info("184: %s no existe todavía; el esquema born-clean lo crea con %s",
                    table, column)
        return
    if _column_exists(conn, table, column):
        logger.info("184: %s.%s ya existe; idempotente", table, column)
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
    logger.info("184: %s.%s agregado (INV-9 resolución cadena de frío)", table, column)


def run(conn) -> None:
    _add_column(conn, "inventory_temperature_excursions", "resolved_by", "TEXT")
    _add_column(conn, "inventory_temperature_excursions", "resolved_at", "TEXT")
    _add_column(conn, "inventory_temperature_excursions", "resolution_note", "TEXT")

# migrations/standalone/173_storage_location_type.py
"""P0-B (§8) — clasificación de ubicaciones técnicas en `storage_locations`.

§8 exige ubicaciones técnicas explícitas (RECEIVING/AVAILABLE/PICKING/QUARANTINE/
DAMAGED/TRANSIT/RETURNS/PRODUCTION), cada una con su UUID, en vez de usar el
`warehouse_id` como si fuera una ubicación física. Esta migración añade la columna
`location_type TEXT` (nullable; NULL = ubicación física de usuario). Aditiva e
idempotente: sólo agrega la columna si aún no existe.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.173")


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(row[1] == column
               for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def run(conn) -> None:
    table = "storage_locations"
    if not _table_exists(conn, table):
        logger.info("173: %s no existe todavía; el esquema born-clean lo crea con "
                    "location_type", table)
        return
    if _column_exists(conn, table, "location_type"):
        logger.info("173: %s.location_type ya existe; idempotente", table)
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN location_type TEXT")
    logger.info("173: %s.location_type agregado (ubicaciones técnicas §8)", table)

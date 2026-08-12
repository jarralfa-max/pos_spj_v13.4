# migrations/standalone/180_inventory_warehouse_location_capacity.py
"""INV-5 (§24) — capacidad declarada de almacenes y ubicaciones.

Agrega `warehouses.capacity`, `warehouses.capacity_uom` y
`storage_locations.capacity`. Igual que la 173 (ubicaciones técnicas):
aditiva e idempotente, valores decimales guardados como TEXT (REGLA CERO —
nunca REAL/float), nulos por defecto (una capacidad desconocida no es cero).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.180")


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(row[1] == column
               for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _add_column(conn, table: str, column: str, ddl_type: str) -> None:
    if not _table_exists(conn, table):
        logger.info("180: %s no existe todavía; el esquema born-clean lo crea con %s",
                    table, column)
        return
    if _column_exists(conn, table, column):
        logger.info("180: %s.%s ya existe; idempotente", table, column)
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
    logger.info("180: %s.%s agregado (INV-5 capacidad)", table, column)


def run(conn) -> None:
    _add_column(conn, "warehouses", "capacity", "TEXT")
    _add_column(conn, "warehouses", "capacity_uom", "TEXT")
    _add_column(conn, "storage_locations", "capacity", "TEXT")

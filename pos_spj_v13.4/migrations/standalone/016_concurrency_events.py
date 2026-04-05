
# db/migrations/versions/002_create_concurrency_events.py
"""
Migración: Crear tabla de eventos de concurrencia para manejo de operaciones distribuidas.
Soporta seguimiento de reintentos y estado final de operaciones en sistema multi-sucursal.
"""
from __future__ import annotations
import sqlite3
import logging
from typing import Optional

logger = logging.getLogger("spj.migrations.concurrency_events")

# -----------------------------------------------------------------------------
# Constantes de esquema
# -----------------------------------------------------------------------------

TABLE_NAME = "concurrency_events"
INDEX_NAME = "idx_concurrency_operation"

SCHEMA_SQL = f"""
BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS {TABLE_NAME}(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    retries INTEGER NOT NULL DEFAULT 0,
    final_status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    device_id TEXT,
    sucursal_id INTEGER NOT NULL DEFAULT 1,
    metadata TEXT,
    -- Restricciones de dominio
    CHECK (retries >= 0),
    CHECK (final_status IN ('PENDING', 'SUCCESS', 'FAILED', 'CONFLICT', 'RETRYING'))
);

CREATE INDEX IF NOT EXISTS {INDEX_NAME}
ON {TABLE_NAME}(operation_id, final_status);

CREATE INDEX IF NOT EXISTS idx_concurrency_cleanup
ON {TABLE_NAME}(created_at, final_status)
WHERE final_status IN ('SUCCESS', 'FAILED');

PRAGMA foreign_keys=ON;

COMMIT;
"""

# -----------------------------------------------------------------------------
# Versión y dependencias
# -----------------------------------------------------------------------------

REVISION = "002"  # Número de migración
DOWN_REVISION = "001"  # Migración anterior (event_log)
DESCRIPTION = "Crea tabla concurrency_events para manejo de concurrencia distribuida"

# -----------------------------------------------------------------------------
# Función de upgrade (aplicar migración)
# -----------------------------------------------------------------------------

def upgrade(conn):
    """Versión simplificada — no gestiona transacciones propias."""
    try:
        # Create table if not exists
        conn.execute("""
            CREATE TABLE IF NOT EXISTS concurrency_events (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id  TEXT    NOT NULL UNIQUE,
                operation_type TEXT   NOT NULL,
                retries       INTEGER NOT NULL DEFAULT 0,
                final_status  TEXT    NOT NULL DEFAULT 'pending',
                created_at    DATETIME NOT NULL DEFAULT (datetime('now')),
                updated_at    DATETIME NOT NULL DEFAULT (datetime('now')),
                device_id     TEXT    NOT NULL DEFAULT 'local',
                sucursal_id   INTEGER NOT NULL DEFAULT 1,
                metadata      TEXT
            )
        """)
        # Safe index creation
        for idx in [
            "CREATE INDEX IF NOT EXISTS idx_ce_operation_id ON concurrency_events(operation_id)",
            "CREATE INDEX IF NOT EXISTS idx_ce_status ON concurrency_events(final_status)",
            "CREATE INDEX IF NOT EXISTS idx_ce_created ON concurrency_events(created_at)",
        ]:
            try:
                conn.execute(idx)
            except Exception:
                pass
        logger.info("016 — concurrency_events OK")
        return True
    except Exception as e:
        logger.warning("016 upgrade: %s", e)
        return False


def up(conn):
    return upgrade(conn)
def up(conn):
    return upgrade(conn)

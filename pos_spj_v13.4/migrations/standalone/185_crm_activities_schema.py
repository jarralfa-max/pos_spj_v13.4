# migrations/standalone/185_crm_activities_schema.py
"""CRM (relationship) bounded context — Activities/Tasks/Notes/Reminders
(CRM-6).

Creates `crm_activities`/`crm_tasks`/`crm_notes`/`crm_reminders` from
``backend/infrastructure/db/schema/crm_schema.py`` (single source of DDL —
same file migrations 182/183 used for Leads/Opportunities). Also adds
`crm_audit_log.activity_id`/`task_id`/`note_id`: that table already existed
after migration 183 with only `lead_id`/`opportunity_id`, so
`CREATE TABLE IF NOT EXISTS` alone would not add the new columns on a
database that already ran 182/183 — explicit, idempotent `ALTER TABLE`
statements are required (same pattern as migrations 180/183).

Numbered 185 (not 184): migration 184 was claimed by
`184_inventory_cold_chain_resolution.py` (an unrelated Inventario change
landed while this phase was in progress) — renumbered to the next free slot
rather than colliding.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.crm_schema import create_crm_schema

logger = logging.getLogger("spj.migrations.185")


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(row[1] == column
               for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _add_column(conn, table: str, column: str, ddl_type: str) -> None:
    if not _table_exists(conn, table):
        logger.info("185: %s no existe todavía; el esquema born-clean lo crea con %s",
                    table, column)
        return
    if _column_exists(conn, table, column):
        logger.info("185: %s.%s ya existe; idempotente", table, column)
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
    logger.info("185: %s.%s agregado (CRM-6 actividades)", table, column)


def run(conn) -> None:
    create_crm_schema(conn)
    _add_column(conn, "crm_audit_log", "activity_id", "TEXT")
    _add_column(conn, "crm_audit_log", "task_id", "TEXT")
    _add_column(conn, "crm_audit_log", "note_id", "TEXT")
    conn.commit()
    logger.info("185: CRM (actividades/tareas/notas/recordatorios) bounded context schema creado.")


up = run

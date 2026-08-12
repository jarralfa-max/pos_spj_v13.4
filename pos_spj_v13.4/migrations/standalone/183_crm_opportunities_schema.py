# migrations/standalone/183_crm_opportunities_schema.py
"""CRM (relationship) bounded context — Opportunities/pipeline (CRM-5).

Creates `crm_stage_definitions`/`opportunities`/`opportunity_stage_history`/
`opportunity_product_interests` from
``backend/infrastructure/db/schema/crm_schema.py`` (single source of DDL —
same file migration 182 used for Leads, `crm` sub-bounded-context owns one
schema file). Also adds `crm_audit_log.opportunity_id`: that table already
existed after migration 182 with only a `lead_id` column, so
`CREATE TABLE IF NOT EXISTS` alone would not add the new column on a
database that already ran 182 — an explicit, idempotent `ALTER TABLE` is
required (same pattern as migration 180).

Seeds a default 6-stage pipeline (Prospección→Calificación→Propuesta→
Negociación→Cerrada Ganada/Cerrada Perdida) via `INSERT OR IGNORE` keyed by
`code` (same idempotent-seed pattern as migration 169). Stages are
configurable data, not a hardcoded enum (§19-22) — this seed only makes the
system usable out of the box; nothing prevents adding/reordering/retiring
stages later via `crm_stage_definitions` directly.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.crm_schema import create_crm_schema
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.183")

# (code, name, sequence_order, probability_default, is_won_stage, is_lost_stage)
_DEFAULT_STAGES = (
    ("PROSPECTING", "Prospección", 1, 10, False, False),
    ("QUALIFICATION", "Calificación", 2, 25, False, False),
    ("PROPOSAL", "Propuesta", 3, 50, False, False),
    ("NEGOTIATION", "Negociación", 4, 75, False, False),
    ("CLOSED_WON", "Cerrada Ganada", 5, 100, True, False),
    ("CLOSED_LOST", "Cerrada Perdida", 6, 0, False, True),
)


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(row[1] == column
               for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _add_column(conn, table: str, column: str, ddl_type: str) -> None:
    if not _table_exists(conn, table):
        logger.info("183: %s no existe todavía; el esquema born-clean lo crea con %s",
                    table, column)
        return
    if _column_exists(conn, table, column):
        logger.info("183: %s.%s ya existe; idempotente", table, column)
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
    logger.info("183: %s.%s agregado (CRM-5 oportunidades)", table, column)


def _seed_default_stages(conn) -> None:
    inserted = 0
    for code, name, sequence_order, probability_default, is_won, is_lost in _DEFAULT_STAGES:
        cur = conn.execute(
            "INSERT OR IGNORE INTO crm_stage_definitions"
            " (id, code, name, sequence_order, probability_default, is_won_stage,"
            " is_lost_stage, required_fields_json, min_activities, active,"
            " created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,'[]',0,1, datetime('now'), datetime('now'))",
            (new_uuid(), code, name, sequence_order, probability_default,
             int(is_won), int(is_lost)))
        inserted += cur.rowcount or 0
    logger.info("183: pipeline por defecto sembrado (%d etapa(s) nueva(s)).", inserted)


def run(conn) -> None:
    create_crm_schema(conn)
    _add_column(conn, "crm_audit_log", "opportunity_id", "TEXT")
    _seed_default_stages(conn)
    conn.commit()
    logger.info("183: CRM (oportunidades/pipeline) bounded context schema creado.")


up = run

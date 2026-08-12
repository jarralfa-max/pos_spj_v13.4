# migrations/standalone/182_crm_bounded_context_schema.py
"""CRM (relationship) bounded context — born-clean UUIDv7 schema (CRM-4).

Creates the canonical leads/qualifications tables and their satellite
audit/outbox tables from
``backend/infrastructure/db/schema/crm_schema.py`` (single source of DDL).
Independent of ``customers_crm_schema.py`` (migration 181) — separate
bounded context, separate schema file, separate migration.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.crm_schema import create_crm_schema

logger = logging.getLogger("spj.migrations.182")


def run(conn) -> None:
    create_crm_schema(conn)
    conn.commit()
    logger.info("182: CRM (leads) bounded context schema created (born-clean UUIDv7).")


up = run

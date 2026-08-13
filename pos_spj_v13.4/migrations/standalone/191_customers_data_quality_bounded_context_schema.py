# migrations/standalone/191_customers_data_quality_bounded_context_schema.py
"""Customer Master bounded context — Calidad/Duplicados/Fusión/Importación
(CRM-11).

Creates `customer_duplicate_candidates`/`customer_merge_records`/
`customer_data_quality_issues`/`customer_import_batches` from
``backend/infrastructure/db/schema/customers_crm_schema.py`` (single source
of DDL — same file migration 181 used for the Customer Master tables).
No ALTER TABLE needed: these are brand-new tables, not new columns on an
existing one, so plain ``CREATE TABLE IF NOT EXISTS`` is idempotent on a
database that already ran 181.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema

logger = logging.getLogger("spj.migrations.191")


def run(conn) -> None:
    create_customers_crm_schema(conn)
    conn.commit()
    logger.info("191: Customer Master (calidad/duplicados/fusión/importación) bounded context schema creado.")


up = run

# migrations/standalone/193_customers_legacy_customer_bridge.py
"""Customer Master — legacy identity bridge (CRM-21, "Migración de
consumidores").

Adds ``customers.legacy_customer_id`` and its partial unique index —
``customers`` already existed after migration 181 without this column, so
``CREATE TABLE IF NOT EXISTS`` alone would not add it on a database that
already ran 181 — an explicit, idempotent ``ALTER TABLE`` is required (same
pattern as migration 192's ``last_purchase_at``/``purchase_count``).

This column lets ``ResolveLegacyCustomerUseCase``/``BackfillLegacyCustomersUseCase``
(``backend/application/customers/use_cases/legacy_customer_bridge_use_cases.py``)
bridge a legacy ``clientes.id`` row to a ``customers`` row without migrating
``clientes`` itself — see that module's docstring for why a full identity
migration is out of scope here.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema

logger = logging.getLogger("spj.migrations.193")


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(row[1] == column
               for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _add_column(conn, table: str, column: str, ddl_type: str) -> None:
    if not _table_exists(conn, table):
        logger.info("193: %s no existe todavía; el esquema born-clean lo crea con %s",
                    table, column)
        return
    if _column_exists(conn, table, column):
        logger.info("193: %s.%s ya existe; idempotente", table, column)
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
    logger.info("193: %s.%s agregado (CRM-21 migración de consumidores)", table, column)


def run(conn) -> None:
    create_customers_crm_schema(conn)
    _add_column(conn, "customers", "legacy_customer_id", "TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_legacy_customer_id ON customers(legacy_customer_id)"
        " WHERE legacy_customer_id IS NOT NULL")
    conn.commit()
    logger.info("193: puente de identidad legacy (CRM-21) creado.")


up = run

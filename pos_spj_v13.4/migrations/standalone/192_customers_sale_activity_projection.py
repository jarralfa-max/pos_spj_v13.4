# migrations/standalone/192_customers_sale_activity_projection.py
"""Customer Master — sale-activity projection columns (CRM-13, §49 Ventas).

Adds ``customers.last_purchase_at``/``customers.purchase_count`` — the
projection ``RecordCustomerSaleActivityUseCase`` updates in reaction to
Ventas' ``SALE_COMPLETED``/``SALE_CANCELLED`` events. ``customers`` already
existed after migration 181 without these columns, so
``CREATE TABLE IF NOT EXISTS`` alone would not add them on a database that
already ran 181 — an explicit, idempotent ``ALTER TABLE`` is required (same
pattern as migration 183's ``crm_audit_log.opportunity_id``).
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema

logger = logging.getLogger("spj.migrations.192")


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _column_exists(conn, table: str, column: str) -> bool:
    return any(row[1] == column
               for row in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _add_column(conn, table: str, column: str, ddl_type: str) -> None:
    if not _table_exists(conn, table):
        logger.info("192: %s no existe todavía; el esquema born-clean lo crea con %s",
                    table, column)
        return
    if _column_exists(conn, table, column):
        logger.info("192: %s.%s ya existe; idempotente", table, column)
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
    logger.info("192: %s.%s agregado (CRM-13 integraciones)", table, column)


def run(conn) -> None:
    create_customers_crm_schema(conn)
    _add_column(conn, "customers", "last_purchase_at", "TEXT")
    _add_column(conn, "customers", "purchase_count", "INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    logger.info("192: proyección de actividad de venta (CRM-13) creada.")


up = run

# migrations/standalone/201_sales_payments_schema.py
"""Sales/POS bounded context — adds `sale_payments` (SALES-12.../POS-13).

`create_sales_schema()`'s DDL already includes `sale_payments` for fresh
creates; this migration exists so a database that already ran migration 198
before this table existed still gets it. `CREATE TABLE IF NOT EXISTS` makes
re-running the whole schema-creation function safe/idempotent for the
already-existing `sales`/`sale_lines`/`sales_outbox` tables too.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.sales_schema import create_sales_schema

logger = logging.getLogger("spj.migrations.201")


def run(conn) -> None:
    create_sales_schema(conn)
    conn.commit()
    logger.info("201: sales.sale_payments asegurada.")


up = run

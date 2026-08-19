# migrations/standalone/204_sales_invoice_requests_schema.py
"""Sales/POS bounded context — adds `sale_invoice_requests` (SALES-18/POS-18).

`create_sales_schema()`'s DDL already includes this table for fresh
creates; this migration exists so a database that already ran migration 198
before this table existed still gets it. `CREATE TABLE IF NOT EXISTS` makes
re-running the whole schema-creation function safe for the already-existing
tables too.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.sales_schema import create_sales_schema

logger = logging.getLogger("spj.migrations.204")


def run(conn) -> None:
    create_sales_schema(conn)
    conn.commit()
    logger.info("204: sales.sale_invoice_requests asegurada.")


up = run

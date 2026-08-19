# migrations/standalone/203_sales_returns_schema.py
"""Sales/POS bounded context — adds `sale_returns` + `sales.reversed_at`
(SALES-16/POS-16).

`create_sales_schema()`'s DDL already includes both for fresh creates; this
migration exists so a database that already ran migration 198 before they
existed still gets them. `create_sales_schema()` is `CREATE TABLE IF NOT
EXISTS`-safe to re-run for the already-existing tables; `reversed_at` needs
its own `ensure_column` since it's a column on an existing table, same
pattern as migrations 199/202.
"""
from __future__ import annotations

import logging

from migrations.m000_base_schema import ensure_column
from backend.infrastructure.db.schema.sales_schema import create_sales_schema

logger = logging.getLogger("spj.migrations.203")


def run(conn) -> None:
    create_sales_schema(conn)
    ensure_column(conn, "sales", "reversed_at TEXT")
    conn.commit()
    logger.info("203: sales.sale_returns + sales.reversed_at aseguradas.")


up = run

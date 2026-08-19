# migrations/standalone/199_sales_inventory_reservation_column.py
"""Sales/POS — adds `sales.inventory_reservation_id` (SALES-9/POS-9).

`backend/infrastructure/db/schema/sales_schema.py`'s own DDL already
includes this column for fresh creates; this migration exists so a database
that already ran migration 198 before this column existed still gets it,
via the idempotent `ensure_column` helper (`ALTER TABLE ... ADD COLUMN`,
no-ops if the column is already there).
"""
from __future__ import annotations

import logging

from migrations.m000_base_schema import ensure_column

logger = logging.getLogger("spj.migrations.199")


def run(conn) -> None:
    ensure_column(conn, "sales", "inventory_reservation_id TEXT")
    conn.commit()
    logger.info("199: sales.inventory_reservation_id asegurada.")


up = run

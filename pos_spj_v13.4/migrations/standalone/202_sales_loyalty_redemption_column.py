# migrations/standalone/202_sales_loyalty_redemption_column.py
"""Sales/POS — adds `sales.loyalty_redeemed_amount` (SALES-14/POS-14).

`create_sales_schema()`'s DDL already includes this column for fresh
creates; this migration exists so a database that already ran migration 198
before this column existed still gets it, via the idempotent `ensure_column`
helper (same pattern as migration 199 for `inventory_reservation_id`).
"""
from __future__ import annotations

import logging

from migrations.m000_base_schema import ensure_column

logger = logging.getLogger("spj.migrations.202")


def run(conn) -> None:
    ensure_column(conn, "sales", "loyalty_redeemed_amount TEXT NOT NULL DEFAULT '0'")
    conn.commit()
    logger.info("202: sales.loyalty_redeemed_amount asegurada.")


up = run

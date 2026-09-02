# migrations/standalone/233_commercial_instruments_vouchers_schema.py
"""Commercial Instruments — Voucher tables (LOY-13, §22): definitions,
instances, transactions (ledger), redemptions.

Extends `create_commercial_instruments_schema()` — same idempotent-
re-invocation pattern as Loyalty's own migrations 227-231.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.commercial_instruments_schema import (
    create_commercial_instruments_schema,
)

logger = logging.getLogger("spj.migrations.233")


def run(conn) -> None:
    create_commercial_instruments_schema(conn)
    conn.commit()
    logger.info("233: voucher tables ensured (definitions/instances/transactions/redemptions).")


up = run

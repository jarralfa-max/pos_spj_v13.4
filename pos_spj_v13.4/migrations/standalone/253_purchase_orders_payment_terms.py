# migrations/standalone/253_purchase_orders_payment_terms.py
"""253 — purchase_orders.payment_terms (PUR-8 audit gap) — extends the schema.

``purchase_orders`` had no payment-terms column at all — ``direct_purchases``
already carries ``payment_condition``, but the enterprise PO flow (§25 of the
procurement spec) never captured it, so downstream CxP due-date calculation
had nothing to read.

Re-runs the idempotent ``create_procurement_schema`` (same pattern as 137 for
Products): DDL lives solely in ``procurement_schema.py``, which now declares
``payment_terms`` on ``purchase_orders`` and guards the column with an ALTER
for tables created by an earlier run of that same function.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema

logger = logging.getLogger("spj.migrations.253")


def run(conn) -> None:
    create_procurement_schema(conn)
    conn.commit()
    logger.info("253: purchase_orders.payment_terms asegurada.")


up = run

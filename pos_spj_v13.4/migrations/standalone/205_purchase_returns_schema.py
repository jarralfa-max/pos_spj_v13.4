# migrations/standalone/205_purchase_returns_schema.py
"""Procurement bounded context — adds `purchase_returns` + `purchase_return_lines`
(devoluciones a proveedor).

Migration 120 already created and froze the canonical procurement schema; it is
marked done in `schema_migrations` on every existing install and will never
re-run, so `create_procurement_schema()` is intentionally left untouched.
`create_purchase_returns_schema()` is a new, separate function in
`backend/infrastructure/db/schema/procurement_schema.py` that creates only the
two new tables (`CREATE TABLE IF NOT EXISTS`-safe, idempotent).

A purchase return references — but never deletes — the original goods receipt
(`goods_receipt_id`) and/or purchase order (`purchase_order_id`).
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.procurement_schema import (
    create_purchase_returns_schema,
)

logger = logging.getLogger("spj.migrations.205")


def run(conn) -> None:
    create_purchase_returns_schema(conn)
    conn.commit()
    logger.info("205: purchase_returns + purchase_return_lines schema created.")


up = run

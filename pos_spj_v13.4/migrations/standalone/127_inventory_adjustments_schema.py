# migrations/standalone/127_inventory_adjustments_schema.py
"""Inventory adjustments (INV-14) — extends the canonical inventory schema.

Adds ``inventory_adjustment`` and ``inventory_adjustment_line`` (born-clean
UUIDv7) by re-running the idempotent ``create_inventory_schema``. DDL lives solely
in inventory_schema.py.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

logger = logging.getLogger("spj.migrations.127")


def run(conn) -> None:
    create_inventory_schema(conn)
    conn.commit()
    logger.info("127: inventory adjustment tables ensured (born-clean UUIDv7).")


up = run

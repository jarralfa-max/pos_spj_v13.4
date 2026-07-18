# migrations/standalone/126_inventory_counts_schema.py
"""Inventory counts (INV-13) — extends the canonical inventory schema.

Adds ``inventory_count`` and ``inventory_count_line`` (born-clean UUIDv7) by
re-running the idempotent ``create_inventory_schema``. DDL lives solely in
inventory_schema.py.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

logger = logging.getLogger("spj.migrations.126")


def run(conn) -> None:
    create_inventory_schema(conn)
    conn.commit()
    logger.info("126: inventory count tables ensured (born-clean UUIDv7).")


up = run

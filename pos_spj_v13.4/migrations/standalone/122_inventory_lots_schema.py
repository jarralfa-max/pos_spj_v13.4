# migrations/standalone/122_inventory_lots_schema.py
"""Inventory lots (INV-7) — extends the canonical inventory schema.

Adds ``inventory_lots`` (born-clean UUIDv7) by re-running the idempotent
``create_inventory_schema`` (CREATE TABLE IF NOT EXISTS), so existing databases
gain only the new table. DDL lives solely in inventory_schema.py.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

logger = logging.getLogger("spj.migrations.122")


def run(conn) -> None:
    create_inventory_schema(conn)
    conn.commit()
    logger.info("122: inventory_lots table ensured (born-clean UUIDv7).")


up = run

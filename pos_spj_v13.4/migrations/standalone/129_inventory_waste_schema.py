# migrations/standalone/129_inventory_waste_schema.py
"""Inventory waste/disposal (INV-16) — extends the canonical inventory schema.

Adds ``inventory_waste_event`` (born-clean UUIDv7) by re-running the idempotent
``create_inventory_schema``. DDL lives solely in inventory_schema.py.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

logger = logging.getLogger("spj.migrations.129")


def run(conn) -> None:
    create_inventory_schema(conn)
    conn.commit()
    logger.info("129: inventory waste-event table ensured (born-clean UUIDv7).")


up = run

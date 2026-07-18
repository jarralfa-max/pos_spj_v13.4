# migrations/standalone/128_inventory_quarantine_schema.py
"""Inventory quarantine (INV-15) — extends the canonical inventory schema.

Adds ``inventory_quarantine`` (born-clean UUIDv7) by re-running the idempotent
``create_inventory_schema``. DDL lives solely in inventory_schema.py.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

logger = logging.getLogger("spj.migrations.128")


def run(conn) -> None:
    create_inventory_schema(conn)
    conn.commit()
    logger.info("128: inventory quarantine table ensured (born-clean UUIDv7).")


up = run

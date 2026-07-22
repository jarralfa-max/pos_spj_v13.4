# migrations/standalone/131_inventory_replenishment_schema.py
"""Inventory replenishment planning (INV-18) — extends the canonical schema.

Adds ``inventory_replenishment_rule`` and ``inventory_replenishment_suggestion``
(born-clean UUIDv7) by re-running the idempotent ``create_inventory_schema``.
Rules hold the min/max/safety/target policy; suggestions are the evaluated
output (purchase vs transfer). DDL lives solely in inventory_schema.py.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

logger = logging.getLogger("spj.migrations.131")


def run(conn) -> None:
    create_inventory_schema(conn)
    conn.commit()
    logger.info("131: inventory replenishment rule/suggestion tables ensured.")


up = run

# migrations/standalone/124_inventory_reservations_schema.py
"""Inventory reservations/allocations (INV-10) — extends the canonical schema.

Adds ``inventory_reservation`` and ``inventory_allocation`` (born-clean UUIDv7)
by re-running the idempotent ``create_inventory_schema``. Canonical names are
singular; the legacy plural ``inventory_reservations`` keeps its readers until
INV-27. DDL lives solely in inventory_schema.py.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

logger = logging.getLogger("spj.migrations.124")


def run(conn) -> None:
    create_inventory_schema(conn)
    conn.commit()
    logger.info("124: inventory reservation/allocation tables ensured (born-clean UUIDv7).")


up = run

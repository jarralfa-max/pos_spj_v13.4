# migrations/standalone/130_inventory_traceability_schema.py
"""Inventory traceability genealogy (INV-17) — extends the canonical schema.

Adds ``inventory_traceability_link`` (born-clean UUIDv7) by re-running the
idempotent ``create_inventory_schema``. The table records explicit parent→child
lot edges for transformations the ledger cannot infer (production/slaughter/
repack), so a recall can walk the genealogy in both directions. DDL lives solely
in inventory_schema.py.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

logger = logging.getLogger("spj.migrations.130")


def run(conn) -> None:
    create_inventory_schema(conn)
    conn.commit()
    logger.info("130: inventory traceability-link table ensured (born-clean UUIDv7).")


up = run

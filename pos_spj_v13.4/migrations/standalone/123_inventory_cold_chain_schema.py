# migrations/standalone/123_inventory_cold_chain_schema.py
"""Inventory cold chain (INV-9) — extends the canonical inventory schema.

Adds ``inventory_temperature_readings`` and ``inventory_temperature_excursions``
(born-clean UUIDv7) by re-running the idempotent ``create_inventory_schema``.
DDL lives solely in inventory_schema.py.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

logger = logging.getLogger("spj.migrations.123")


def run(conn) -> None:
    create_inventory_schema(conn)
    conn.commit()
    logger.info("123: inventory cold-chain tables ensured (born-clean UUIDv7).")


up = run

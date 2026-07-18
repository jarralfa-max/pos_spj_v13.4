# migrations/standalone/125_inventory_transfers_schema.py
"""Inventory transfers (INV-12) — extends the canonical inventory schema.

Adds ``inventory_transfer`` and ``inventory_transfer_line`` (born-clean UUIDv7)
by re-running the idempotent ``create_inventory_schema``. Consolidates the three
legacy transfer tables (transferencias/transferencias_inventario/traspasos),
which keep their readers until INV-27. DDL lives solely in inventory_schema.py.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

logger = logging.getLogger("spj.migrations.125")


def run(conn) -> None:
    create_inventory_schema(conn)
    conn.commit()
    logger.info("125: inventory transfer tables ensured (born-clean UUIDv7).")


up = run

# migrations/standalone/121_inventory_bounded_context_schema.py
"""Inventory bounded context — born-clean UUIDv7 schema.

Creates the canonical inventory tables (configurable limits, warehouses/zones/
locations, the movement ledger + lines, the balance projection, inventory
settings, hot-authorization + audit logs, transactional outbox + processed
events) from ``backend/infrastructure/db/schema/inventory_schema.py`` (single
source of DDL).

The legacy/partial inventory tables (inventario_actual, inventory_stock,
branch_inventory, movimientos_inventario, transferencias/traspasos…) still have
live readers and are NOT touched here — their readers migrate in INV-6/INV-11
and the tables drop in INV-27 (see inventory_schema_consolidation.md).
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

logger = logging.getLogger("spj.migrations.121")


def run(conn) -> None:
    create_inventory_schema(conn)
    conn.commit()
    logger.info("121: inventory bounded context schema created (born-clean UUIDv7).")


up = run

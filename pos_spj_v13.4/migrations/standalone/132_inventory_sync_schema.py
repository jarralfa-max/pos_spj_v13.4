# migrations/standalone/132_inventory_sync_schema.py
"""Inventory offline-first sync (INV-22) — extends the canonical schema.

Adds ``inventory_sync_dispatch`` (per-node sequence + retry/backoff +
dead-letter) and ``inventory_sync_cursor`` (per node/stream sync progress) by
re-running the idempotent ``create_inventory_schema``. DDL lives solely in
inventory_schema.py.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

logger = logging.getLogger("spj.migrations.132")


def run(conn) -> None:
    create_inventory_schema(conn)
    conn.commit()
    logger.info("132: inventory sync dispatch/cursor tables ensured (offline-first).")


up = run

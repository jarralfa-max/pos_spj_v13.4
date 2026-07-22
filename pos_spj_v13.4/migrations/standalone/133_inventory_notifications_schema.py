# migrations/standalone/133_inventory_notifications_schema.py
"""Inventory notifications / WhatsApp alerts (INV-23) — extends the schema.

Adds ``inventory_notification_rule`` (routing: event→recipient/channel/severity)
and ``inventory_notification_log`` (audit + idempotency via UNIQUE dedupe_key +
throttle source) by re-running the idempotent ``create_inventory_schema``. DDL
lives solely in inventory_schema.py.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

logger = logging.getLogger("spj.migrations.133")


def run(conn) -> None:
    create_inventory_schema(conn)
    conn.commit()
    logger.info("133: inventory notification rule/log tables ensured.")


up = run

# migrations/standalone/147_products_notifications_schema.py
"""Products notifications schema (PROD-16).

Adds ``product_notification_log`` (severity, channel, throttle, audit) by
re-running the idempotent ``create_products_schema``. DDL lives solely in
``products_schema.py``.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.147")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("147: product_notification_log ensured.")


up = run

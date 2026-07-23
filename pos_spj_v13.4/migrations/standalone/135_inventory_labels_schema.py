# migrations/standalone/135_inventory_labels_schema.py
"""Inventory labels / printing audit (INV-26) — extends the schema.

Adds ``inventory_label_print_log`` (audit + reprint trail for lot/weight/
transfer/count/adjustment labels) by re-running the idempotent
``create_inventory_schema``. DDL lives solely in inventory_schema.py.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

logger = logging.getLogger("spj.migrations.135")


def run(conn) -> None:
    create_inventory_schema(conn)
    conn.commit()
    logger.info("135: inventory_label_print_log ensured.")


up = run

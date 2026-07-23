# migrations/standalone/140_products_quality_shelf_life_schema.py
"""Products quality / shelf-life / logistics profiles schema (PROD-8).

Adds ``product_shelf_life_profiles``, ``product_quality_profiles`` and
``product_logistics_profiles`` by re-running the idempotent
``create_products_schema``. DDL lives solely in ``products_schema.py``.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.140")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("140: shelf-life / quality / logistics profiles ensured.")


up = run

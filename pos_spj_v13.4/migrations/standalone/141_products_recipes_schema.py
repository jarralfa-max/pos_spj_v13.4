# migrations/standalone/141_products_recipes_schema.py
"""Products recipes / BOM schema (PROD-9).

Adds ``recipes``, ``recipe_versions`` (versioned §22), ``recipe_components`` and
``recipe_outputs`` (Decimal quantities) by re-running the idempotent
``create_products_schema``. DDL lives solely in ``products_schema.py``.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.141")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("141: recipes / recipe_versions / components / outputs ensured.")


up = run

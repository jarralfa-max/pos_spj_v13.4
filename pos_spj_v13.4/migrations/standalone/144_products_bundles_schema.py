# migrations/standalone/144_products_bundles_schema.py
"""Products bundles / combos / kits schema (PROD-13).

Adds ``product_bundles``, ``bundle_versions`` (versioned) and
``bundle_components`` (Decimal quantities) by re-running the idempotent
``create_products_schema``. DDL lives solely in ``products_schema.py``.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.144")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("144: product_bundles / versions / components ensured.")


up = run

# migrations/standalone/137_products_units_catch_weight_schema.py
"""Products units / conversions / catch-weight schema (PROD-5) — extends the schema.

Adds ``units_of_measure``, ``product_unit_conversions`` (Decimal factor, no REAL)
and ``product_catch_weight_config`` (range/tolerance/price basis/scale barcode) by
re-running the idempotent ``create_products_schema``. DDL lives solely in
``products_schema.py``.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.137")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("137: units_of_measure / conversions / catch-weight config ensured.")


up = run

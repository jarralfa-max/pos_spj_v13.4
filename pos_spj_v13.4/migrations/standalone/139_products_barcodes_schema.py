# migrations/standalone/139_products_barcodes_schema.py
"""Products barcodes / alternate codes schema (PROD-7) — extends the schema.

Adds ``product_barcodes`` (with a partial UNIQUE index enforcing that an *active*
barcode value belongs to one product, §17) and ``product_alternate_codes`` by
re-running the idempotent ``create_products_schema``. DDL lives solely in
``products_schema.py``.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.139")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("139: product_barcodes / product_alternate_codes ensured.")


up = run

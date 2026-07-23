# migrations/standalone/146_products_external_catalogs_schema.py
"""Products external catalogs / import schema (PROD-15).

Adds ``external_catalog_sources``, ``external_product_records`` (with provenance,
data-quality score, matching) and ``product_import_batches`` by re-running the
idempotent ``create_products_schema``. DDL lives solely in ``products_schema.py``.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.146")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("146: external catalog sources / records / import batches ensured.")


up = run

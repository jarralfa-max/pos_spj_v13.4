# migrations/standalone/145_products_branch_assortment_schema.py
"""Products branch / assortment schema (PROD-14).

Adds ``branch_product`` (canonical singular — per-branch enablement, no price/
stock), ``assortments`` and ``assortment_products`` (per-channel curated sets) by
re-running the idempotent ``create_products_schema``. The legacy plural
``branch_products`` (with precio_local) is untouched here and removed in PROD-19.
DDL lives solely in ``products_schema.py``.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.145")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("145: branch_product / assortments / assortment_products ensured.")


up = run

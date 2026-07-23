# migrations/standalone/142_products_yield_profiles_schema.py
"""Products yield-profiles schema (PROD-10).

Adds ``yield_profiles``, ``yield_profile_versions`` (versioned, configurable
tolerance) and ``yield_outputs`` (Decimal yields, min/max band) by re-running the
idempotent ``create_products_schema``. DDL lives solely in ``products_schema.py``.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.142")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("142: yield_profiles / versions / outputs ensured.")


up = run

# migrations/standalone/143_products_cutting_schemes_schema.py
"""Products cutting-schemes schema (PROD-11).

Adds ``cutting_schemes``, ``cutting_scheme_versions`` (versioned) and
``cutting_outputs`` (Decimal by piece/weight, bone status) by re-running the
idempotent ``create_products_schema``. DDL lives solely in ``products_schema.py``.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.143")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("143: cutting_schemes / versions / outputs ensured.")


up = run

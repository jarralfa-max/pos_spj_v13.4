# migrations/standalone/138_products_internal_stage.py
"""Products internal / WIP stage column (PROD-6).

Ensures ``products.internal_stage`` exists (NONE | INTERNAL_ONLY | WORK_IN_
PROGRESS | SEMI_FINISHED | PROCESS_INTERMEDIATE). Idempotent: re-runs the schema
(no-op for fresh DBs) and adds the column on pre-existing DBs via a guarded ALTER.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.138")


def run(conn) -> None:
    create_products_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(products)")}
    if "internal_stage" not in cols:
        conn.execute(
            "ALTER TABLE products ADD COLUMN internal_stage TEXT NOT NULL DEFAULT 'NONE'")
    conn.commit()
    logger.info("138: products.internal_stage ensured.")


up = run

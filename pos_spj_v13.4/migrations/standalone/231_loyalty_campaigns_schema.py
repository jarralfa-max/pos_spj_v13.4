# migrations/standalone/231_loyalty_campaigns_schema.py
"""Fidelidad/Loyalty — Campaign table (LOY-11, §19).

Extends `create_loyalty_schema()` — same idempotent-re-invocation pattern as
migrations 227-230. `loyalty_campaigns` is distinct from the unrelated
`marketing_campaigns` table (Settings/Document Output, migration 215).
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema

logger = logging.getLogger("spj.migrations.231")


def run(conn) -> None:
    create_loyalty_schema(conn)
    conn.commit()
    logger.info("231: loyalty_campaigns schema ensured.")


up = run

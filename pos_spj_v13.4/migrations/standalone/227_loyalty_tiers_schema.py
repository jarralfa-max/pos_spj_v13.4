# migrations/standalone/227_loyalty_tiers_schema.py
"""Fidelidad/Loyalty — LoyaltyTier / LoyaltyTierHistory tables (LOY-7, §14).

Extends `backend/infrastructure/db/schema/loyalty_schema.py::create_loyalty_schema`
(now also declares `loyalty_tiers`/`loyalty_tier_history`) rather than adding
a sibling schema module — same pattern CRM-26 used for its own 2-table
addition to an existing schema file (migration 194). Re-invoking
`create_loyalty_schema()` here is safe/idempotent (`CREATE TABLE IF NOT
EXISTS`) even against a database that already ran migration 225 — only the
2 new tables get created, the 5 from 225 are no-ops.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema

logger = logging.getLogger("spj.migrations.227")


def run(conn) -> None:
    create_loyalty_schema(conn)
    conn.commit()
    logger.info("227: loyalty_tiers/loyalty_tier_history schema ensured.")


up = run

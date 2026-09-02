# migrations/standalone/237_loyalty_card_templates_schema.py
"""Loyalty Card templates + template versions (LOY-17, §33-34).

Re-invokes `create_loyalty_cards_schema()` (idempotent `CREATE TABLE IF NOT
EXISTS`) — same "extend the one schema function, re-run it from a new
migration number" pattern already used by every other LOY-N schema-
extension migration in this pipeline (e.g. 227-231 for Loyalty).
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.loyalty_cards_schema import create_loyalty_cards_schema

logger = logging.getLogger("spj.migrations.237")


def run(conn) -> None:
    create_loyalty_cards_schema(conn)
    conn.commit()
    logger.info("237: loyalty_card_templates/loyalty_card_template_versions schema ensured.")


up = run

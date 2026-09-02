# migrations/standalone/241_loyalty_digital_card_projections_schema.py
"""Loyalty digital card projections (LOY-23, §48). Re-invokes
`create_loyalty_cards_schema()` (idempotent), same schema-extension pattern
as migrations 237-240.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.loyalty_cards_schema import create_loyalty_cards_schema

logger = logging.getLogger("spj.migrations.241")


def run(conn) -> None:
    create_loyalty_cards_schema(conn)
    conn.commit()
    logger.info("241: loyalty_digital_card_projections schema ensured.")


up = run

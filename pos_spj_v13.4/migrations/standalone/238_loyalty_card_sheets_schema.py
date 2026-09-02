# migrations/standalone/238_loyalty_card_sheets_schema.py
"""Loyalty Card sheet + imposition profiles (LOY-20, §38-40: "Pliegos
12x18"). Re-invokes `create_loyalty_cards_schema()` (idempotent), same
schema-extension pattern as migration 237.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.loyalty_cards_schema import create_loyalty_cards_schema

logger = logging.getLogger("spj.migrations.238")


def run(conn) -> None:
    create_loyalty_cards_schema(conn)
    conn.commit()
    logger.info(
        "238: loyalty_card_sheet_profiles/loyalty_card_imposition_profiles schema ensured.")


up = run

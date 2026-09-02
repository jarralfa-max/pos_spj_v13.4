# migrations/standalone/239_loyalty_card_batches_schema.py
"""Loyalty Card batches + batch items (LOY-21, §43-44). Re-invokes
`create_loyalty_cards_schema()` (idempotent), same schema-extension pattern
as migrations 237/238.

Verified no collision against the legacy `card_batches` table
(`m000_base_schema.py`) — new tables are `loyalty_card_batches`/
`loyalty_card_batch_items`.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.loyalty_cards_schema import create_loyalty_cards_schema

logger = logging.getLogger("spj.migrations.239")


def run(conn) -> None:
    create_loyalty_cards_schema(conn)
    conn.commit()
    logger.info("239: loyalty_card_batches/loyalty_card_batch_items schema ensured.")


up = run

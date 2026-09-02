# migrations/standalone/228_loyalty_rewards_schema.py
"""Fidelidad/Loyalty — Reward / RewardRedemption tables (LOY-8, §15).

Extends `create_loyalty_schema()` (now also declares `loyalty_rewards`/
`loyalty_reward_redemptions`) — same idempotent-re-invocation pattern as
migration 227.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema

logger = logging.getLogger("spj.migrations.228")


def run(conn) -> None:
    create_loyalty_schema(conn)
    conn.commit()
    logger.info("228: loyalty_rewards/loyalty_reward_redemptions schema ensured.")


up = run

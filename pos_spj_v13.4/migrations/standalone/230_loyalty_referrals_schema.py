# migrations/standalone/230_loyalty_referrals_schema.py
"""Fidelidad/Loyalty — Referral table (LOY-10, §17).

Extends `create_loyalty_schema()` — same idempotent-re-invocation pattern as
migrations 227-229.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema

logger = logging.getLogger("spj.migrations.230")


def run(conn) -> None:
    create_loyalty_schema(conn)
    conn.commit()
    logger.info("230: loyalty_referrals schema ensured.")


up = run

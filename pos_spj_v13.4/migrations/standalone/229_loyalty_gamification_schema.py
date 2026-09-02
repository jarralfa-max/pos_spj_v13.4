# migrations/standalone/229_loyalty_gamification_schema.py
"""Fidelidad/Loyalty — gamification tables (LOY-9, §16): challenge
definitions, per-member progress, streaks, badges.

Extends `create_loyalty_schema()` — same idempotent-re-invocation pattern as
migrations 227/228. Uses `loyalty_challenge_definitions`/
`loyalty_challenge_member_progress`, NOT the plain `loyalty_challenges`/
`loyalty_challenge_progress` names — those already belong to the legacy
Growth Engine schema (`migrations/m000_base_schema.py::_create_loyalty`),
same collision class already found/fixed for `loyalty_programs` (LOY-3).
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema

logger = logging.getLogger("spj.migrations.229")


def run(conn) -> None:
    create_loyalty_schema(conn)
    conn.commit()
    logger.info("229: loyalty gamification schema ensured (challenges/streaks/badges).")


up = run

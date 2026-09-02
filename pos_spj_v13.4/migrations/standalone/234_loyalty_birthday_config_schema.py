# migrations/standalone/234_loyalty_birthday_config_schema.py
"""Fidelidad/Loyalty — BirthdayBenefitConfig table (LOY-14, §18).

Extends `create_loyalty_schema()` — same idempotent-re-invocation pattern as
migrations 227-231.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema

logger = logging.getLogger("spj.migrations.234")


def run(conn) -> None:
    create_loyalty_schema(conn)
    conn.commit()
    logger.info("234: loyalty_birthday_configs schema ensured.")


up = run

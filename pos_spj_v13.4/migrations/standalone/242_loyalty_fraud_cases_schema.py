# migrations/standalone/242_loyalty_fraud_cases_schema.py
"""FraudCase schema (LOY-26, §29). Re-invokes `create_loyalty_schema()`
(idempotent), same schema-extension pattern as migrations 227-234."""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema

logger = logging.getLogger("spj.migrations.242")


def run(conn) -> None:
    create_loyalty_schema(conn)
    conn.commit()
    logger.info("242: loyalty_fraud_cases schema ensured.")


up = run

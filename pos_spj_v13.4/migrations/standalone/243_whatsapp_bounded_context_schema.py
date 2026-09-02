# migrations/standalone/243_whatsapp_bounded_context_schema.py
"""WhatsApp channel schema (WA-3, §9/§14-15/§19-21/§61). Creates the 12
canonical tables for the WA-2 domain entities plus inbox/outbox/business-
operation-idempotency/dead-letter. Same schema-module-delegation pattern as
migrations 226/227-234/242 (orders_delivery, loyalty). Idempotent
(`CREATE TABLE IF NOT EXISTS`); does not touch any existing WhatsApp table —
see `backend/infrastructure/db/schema/whatsapp_schema.py` module docstring
for why."""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema

logger = logging.getLogger("spj.migrations.243")


def run(conn) -> None:
    create_whatsapp_schema(conn)
    conn.commit()
    logger.info("243: whatsapp bounded-context schema ensured.")


up = run

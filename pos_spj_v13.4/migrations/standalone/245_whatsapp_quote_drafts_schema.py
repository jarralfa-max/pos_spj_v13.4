# migrations/standalone/245_whatsapp_quote_drafts_schema.py
"""WA-11 (§37). Agrega `whatsapp_quote_drafts`/`whatsapp_quote_draft_lines`
al esquema del canal WhatsApp — el equivalente de `whatsapp_order_drafts`
(migración 244) para cotizaciones. Re-invoca `create_whatsapp_schema()`
(idempotente, mismo módulo de las migraciones 243/244)."""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema

logger = logging.getLogger("spj.migrations.245")


def run(conn) -> None:
    create_whatsapp_schema(conn)
    conn.commit()
    logger.info("245: whatsapp_quote_drafts schema ensured.")


up = run

# migrations/standalone/244_whatsapp_order_drafts_schema.py
"""WA-10 (§34-35). Agrega `whatsapp_order_drafts`/`whatsapp_order_draft_lines`
al esquema del canal WhatsApp (migración 243) — el carrito conversacional,
nunca el pedido canónico. Re-invoca `create_whatsapp_schema()` (idempotente,
mismo patrón que las migraciones 227-234/242 para loyalty)."""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema

logger = logging.getLogger("spj.migrations.244")


def run(conn) -> None:
    create_whatsapp_schema(conn)
    conn.commit()
    logger.info("244: whatsapp_order_drafts schema ensured.")


up = run

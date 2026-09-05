# migrations/standalone/246_whatsapp_delivery_requests_schema.py
"""WA-13. Agrega `whatsapp_delivery_requests` al esquema del canal
WhatsApp — el rastro conversacional de "programar entrega para el pedido
X". Re-invoca `create_whatsapp_schema()` (idempotente, mismo módulo de
las migraciones 243/244/245)."""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema

logger = logging.getLogger("spj.migrations.246")


def run(conn) -> None:
    create_whatsapp_schema(conn)
    conn.commit()
    logger.info("246: whatsapp_delivery_requests schema ensured.")


up = run

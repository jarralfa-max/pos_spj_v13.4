# migrations/standalone/247_whatsapp_handoff_requests_schema.py
"""WA-16. Agrega `whatsapp_handoff_requests` al esquema del canal
WhatsApp. Re-invoca `create_whatsapp_schema()` (idempotente, mismo módulo
de las migraciones 243/244/245/246)."""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema

logger = logging.getLogger("spj.migrations.247")


def run(conn) -> None:
    create_whatsapp_schema(conn)
    conn.commit()
    logger.info("247: whatsapp_handoff_requests schema ensured.")


up = run

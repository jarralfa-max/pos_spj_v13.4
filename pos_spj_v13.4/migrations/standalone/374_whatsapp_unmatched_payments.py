# migrations/standalone/374_whatsapp_unmatched_payments.py
"""SDLC-WA-001. Agrega `whatsapp_unmatched_payments` (bandeja de pagos de
MercadoPago que no casaron con una venta) al esquema del canal WhatsApp.
Re-invoca `create_whatsapp_schema()` (idempotente, mismo módulo de las
migraciones 243-247)."""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.whatsapp_schema import create_whatsapp_schema

logger = logging.getLogger("spj.migrations.374")


def run(conn) -> None:
    create_whatsapp_schema(conn)
    conn.commit()
    logger.info("374: whatsapp_unmatched_payments schema ensured.")


up = run

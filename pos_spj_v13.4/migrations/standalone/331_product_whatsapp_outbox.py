# migrations/standalone/331_product_whatsapp_outbox.py
"""PROD-22 — cola de salida de las alertas de Productos por WhatsApp (§36).

Crea `product_whatsapp_outbox` vía el esquema canónico. El notificador ya no
envía directo: encola, y un servicio de fondo de la app reintenta con espera
creciente; antes una alerta disparada sin conexión se perdía. Idempotente.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.331")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("331: cola de WhatsApp de Productos asegurada.")


up = run

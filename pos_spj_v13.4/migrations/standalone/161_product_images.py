# migrations/standalone/161_product_images.py
"""P1 — tabla de galería de imágenes de producto.

Crea `product_images` vía el esquema canónico. Idempotente. Sin datos semilla.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.161")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("161: tabla product_images asegurada.")


up = run

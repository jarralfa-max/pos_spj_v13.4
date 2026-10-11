# migrations/standalone/323_product_image_background_removal.py
"""PROD-21 — quitar el fondo de la imagen de producto.

Agrega a `product_images` las columnas `source_uri` (el original que se conserva
al quitar el fondo) y `background_removed`, vía el esquema canónico de Productos
(única fuente del DDL). Idempotente. Sin datos semilla: las imágenes existentes
quedan como originales (`background_removed = 0`).
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.323")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("323: product_images.source_uri/background_removed asegurados.")


up = run

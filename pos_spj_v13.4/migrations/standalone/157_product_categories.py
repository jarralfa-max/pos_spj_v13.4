# migrations/standalone/157_product_categories.py
"""P1-01 — tabla de categorías jerárquicas de producto.

Crea `product_categories` (árbol con ruta materializada + profundidad) vía el
esquema canónico. Idempotente: `CREATE TABLE IF NOT EXISTS`. No siembra datos — las
categorías las captura el usuario desde la gestión del catálogo.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.157")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("157: tabla product_categories asegurada.")


up = run

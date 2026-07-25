# migrations/standalone/158_product_brands.py
"""P1-02 — tabla del catálogo plano de marcas de producto.

Crea `product_brands` vía el esquema canónico. Idempotente: `CREATE TABLE IF NOT
EXISTS`. Sin datos semilla — las marcas las captura el usuario desde la gestión.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.158")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("158: tabla product_brands asegurada.")


up = run

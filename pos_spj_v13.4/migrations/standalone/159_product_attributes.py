# migrations/standalone/159_product_attributes.py
"""P1-03 — tablas de atributos configurables y sus opciones enumeradas.

Crea `product_attributes` / `product_attribute_options` vía el esquema canónico.
Idempotente: `CREATE TABLE IF NOT EXISTS`. Sin datos semilla — los atributos y sus
opciones los captura el usuario desde la gestión.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.159")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("159: tablas product_attributes / product_attribute_options aseguradas.")


up = run

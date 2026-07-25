# migrations/standalone/160_product_variants.py
"""P1-03 — soporte de variantes: parent_product_id + asignaciones de atributo.

Asegura la columna ``products.parent_product_id`` y la tabla
``product_variant_assignments`` (vía el esquema canónico). Idempotente. Sin datos
semilla — las variantes se generan desde el producto padre.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.160")


def _column_exists(conn, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def run(conn) -> None:
    create_products_schema(conn)
    # DB previa a P1-03: `products` ya existe sin la columna → agregarla in situ.
    if not _column_exists(conn, "products", "parent_product_id"):
        conn.execute("ALTER TABLE products ADD COLUMN parent_product_id TEXT")
    conn.commit()
    logger.info("160: variantes de producto aseguradas.")


up = run

# migrations/standalone/164_product_import_staging.py
"""Importación CSV/XLSX — tablas de staging (jobs + filas).

Crea `product_import_jobs` / `product_import_rows` vía el esquema canónico.
Idempotente. Sin datos semilla — los batches se crean al importar un archivo.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.164")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("164: tablas de staging de importación aseguradas.")


up = run

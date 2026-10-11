# migrations/standalone/326_product_meat_classification.py
"""PROD-22 — clasificación cárnica del producto (§11).

Crea `product_meat_classifications` (categoría cárnica, región anatómica y corte
de un producto) vía el esquema canónico. Los catálogos de regiones y cortes y la
política que valida su coherencia con la especie ya existían; faltaba dónde
guardar la clasificación de cada producto. Idempotente, sin datos semilla.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema

logger = logging.getLogger("spj.migrations.326")


def run(conn) -> None:
    create_products_schema(conn)
    conn.commit()
    logger.info("326: product_meat_classifications asegurada.")


up = run

# migrations/standalone/328_external_catalog_source_and_reviewer.py
"""PROD-22 — catálogo externo utilizable (§15, §39).

1. `external_product_records.staged_by` (vía el esquema canónico): quién trajo
   el registro; sin él, quien buscaba e importaba podía aprobar lo suyo.
2. Registra la fuente Open Food Facts. El flujo buscar → revisar → aprobar →
   importar existía (PROD-15) pero NO había ninguna fuente en
   `external_catalog_sources`: la búsqueda respondía «La fuente externa no
   existe». Sólo `INSERT OR IGNORE` por código: no toca una fuente que el
   usuario ya haya configurado.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.328")


def run(conn) -> None:
    create_products_schema(conn)
    exists = conn.execute(
        "SELECT 1 FROM external_catalog_sources WHERE code='OPEN_FOOD_FACTS'").fetchone()
    if exists is None:
        conn.execute(
            "INSERT INTO external_catalog_sources (id, code, name, provider_type, endpoint, "
            "active) VALUES (?, 'OPEN_FOOD_FACTS', 'Open Food Facts', 'OPEN_FOOD_FACTS', "
            "'https://world.openfoodfacts.org', 1)", (new_uuid(),))
    conn.commit()
    logger.info("328: fuente Open Food Facts y staged_by asegurados.")


up = run

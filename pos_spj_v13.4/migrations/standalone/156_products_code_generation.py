# migrations/standalone/156_products_code_generation.py
"""P0-04 — tablas + reglas semilla de generación automática de código de producto.

Crea `product_code_generation_rules` / `product_code_sequences` (vía el esquema
canónico) y siembra reglas por tipo de producto (idempotente por scope). El código
se genera offline como PREFIJO-000001 con secuencia transaccional por prefijo.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.156")

# (scope_type, scope_value, prefix)
_RULES = (
    ("DEFAULT", "", "PRD"),
    ("PRODUCT_TYPE", "RESALE_PRODUCT", "ABR"),
    ("PRODUCT_TYPE", "RAW_MATERIAL", "MP"),
    ("PRODUCT_TYPE", "PRIMARY_CUT", "CAR"),
    ("PRODUCT_TYPE", "SECONDARY_CUT", "CAR"),
    ("PRODUCT_TYPE", "GROUND_MEAT", "CAR"),
    ("PRODUCT_TYPE", "OFFAL", "CAR"),
    ("PRODUCT_TYPE", "CARCASS", "CAR"),
    ("PRODUCT_TYPE", "SERVICE", "SER"),
    ("PRODUCT_TYPE", "PACKAGING_MATERIAL", "EMP"),
    ("PRODUCT_TYPE", "MRO_MATERIAL", "MRO"),
    ("PRODUCT_TYPE", "SPARE_PART", "REF"),
    ("PRODUCT_TYPE", "VIRTUAL_BUNDLE", "COM"),
    ("PRODUCT_TYPE", "STOCKED_KIT", "KIT"),
    ("PRODUCT_TYPE", "FINISHED_GOOD", "PT"),
    ("PRODUCT_TYPE", "SEMI_FINISHED_GOOD", "SEMI"),
)


def run(conn) -> None:
    create_products_schema(conn)
    n = 0
    for scope_type, scope_value, prefix in _RULES:
        cur = conn.execute(
            "INSERT OR IGNORE INTO product_code_generation_rules "
            "(id, scope_type, scope_value, prefix, padding) VALUES (?,?,?,?,6)",
            (new_uuid(), scope_type, scope_value, prefix))
        n += cur.rowcount or 0
    conn.commit()
    logger.info("156: reglas de código sembradas (%d nuevas).", n)


up = run

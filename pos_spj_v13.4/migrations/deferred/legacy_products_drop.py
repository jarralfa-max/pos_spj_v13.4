# migrations/deferred/legacy_products_drop.py
"""DEFERRED, ENV-GUARDED drop of the legacy products tables (PROD-19).

This is NOT registered in migrations/engine.py and never runs automatically.
Run it manually ONLY after:
  1. the canonical `products` master is backfilled (migration 148) and is the
     source of truth,
  2. every legacy operational read/write of `productos` and the legacy recipe /
     yield tables has been repointed to the canonical products schema, and
  3. price/stock reads have moved to Pricing / Inventory.

Because it destroys data with (historically) live readers, it refuses to run
unless ``PRODUCTS_ALLOW_LEGACY_DROP=1`` is set. Uses DROP TABLE IF EXISTS so a
partial legacy schema is fine.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("spj.migrations.legacy_products_drop")

_ENV_GUARD = "PRODUCTS_ALLOW_LEGACY_DROP"

# Maestro legacy + surtido legacy con precio_local.
LEGACY_MASTER_TABLES = (
    "branch_products",           # plural legacy (precio_local/stock_min_local)
    "productos",                 # maestro legacy (existencia/precio/categoria texto)
)

# 8 sistemas de recetas paralelos (products_schema_consolidation.md §5).
LEGACY_RECIPE_TABLES = (
    "recetas", "receta_componentes", "product_recipes", "product_recipe_components",
    "product_recipes_abarrotes", "componentes_producto", "paquetes_componentes",
    "recipe_dependency_graph",
)

# Rendimientos solo-pollo / hardcodeados (§6).
LEGACY_YIELD_TABLES = (
    "rendimiento_pollo", "rendimiento_derivados", "meat_production_yields",
    "production_yield_analysis",
)

# Cortes / subproductos legacy.
LEGACY_CLASSIFICATION_TABLES = (
    "cortes_caja_erp", "inventario_subproductos",
)

# Trigger legacy de guard de borrado.
LEGACY_TRIGGERS = (
    "trg_productos_deletion_guard",
)

ALL_LEGACY_TABLES = (
    LEGACY_MASTER_TABLES + LEGACY_RECIPE_TABLES + LEGACY_YIELD_TABLES
    + LEGACY_CLASSIFICATION_TABLES
)


def run(conn) -> list[str]:
    if os.environ.get(_ENV_GUARD) != "1":
        raise RuntimeError(
            f"Rechazado: define {_ENV_GUARD}=1 para ejecutar el DROP destructivo "
            "del legacy de Productos (irreversible).")
    dropped: list[str] = []
    for trigger in LEGACY_TRIGGERS:
        conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    for table in ALL_LEGACY_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    conn.commit()
    logger.warning("legacy_products_drop: %d tablas legacy eliminadas.", len(dropped))
    return dropped


up = run

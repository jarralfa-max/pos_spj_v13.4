# migrations/standalone/148_products_backfill_from_legacy.py
"""PROD-19 corte paso 1 — backfill del maestro legacy `productos` → `products`.

Copia (idempotente, INSERT OR IGNORE por id) las filas del maestro legacy Spanish
``productos`` al maestro canónico born-clean ``products``. Los ids ya son UUID
(TEXT), así que se preservan tal cual — no hay remapeo.

Reglas del corte:
- NO se copian ``precio`` ni ``existencia`` (van a Pricing / Inventory; guardrail
  ``test_product_master_does_not_store_stock`` / ``..._does_not_own_pricing``).
- ``categoria``/``unidad`` legacy son texto libre: la unidad se conserva como
  ``base_unit_id`` textual (placeholder) y ``category_id`` queda NULL (se resuelve
  al mapear catálogos). Los productos incompletos disparan la alerta PRODUCT_
  INCOMPLETE (PROD-16).
- Es aditivo: ``productos`` sigue intacto y los 78 consumidores legacy siguen
  funcionando hasta que se repunten en los pasos siguientes del corte.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.148")

_BACKFILL = """
INSERT OR IGNORE INTO products (
    id, code, name, name_normalized, short_name, description,
    product_type, lifecycle_status, category_id, species_id, base_unit_id,
    internal_stage, sellable, purchasable, inventory_managed, producible,
    internal_only, recipe_allowed, bundle_allowed, lot_controlled,
    serial_controlled, expiration_controlled, catch_weight_enabled,
    quality_controlled, traceability_required, created_at, updated_at)
SELECT
    p.id,
    UPPER(COALESCE(NULLIF(TRIM(p.codigo), ''), 'P-' || SUBSTR(REPLACE(p.id,'-',''),1,10))),
    COALESCE(NULLIF(TRIM(p.nombre), ''), 'Producto ' || SUBSTR(p.id,1,8)),
    COALESCE(NULLIF(TRIM(p.nombre_normalizado), ''), LOWER(TRIM(p.nombre))),
    NULL,
    p.descripcion,
    CASE
        WHEN COALESCE(p.es_paquete,0)=1 THEN 'VIRTUAL_BUNDLE'
        WHEN COALESCE(p.es_subproducto,0)=1 THEN 'BY_PRODUCT'
        WHEN COALESCE(p.es_carnico,0)=1 THEN 'RAW_MATERIAL'
        ELSE 'RESALE_PRODUCT'
    END,
    CASE
        WHEN p.deleted_at IS NOT NULL THEN 'ARCHIVED'
        WHEN COALESCE(p.activo, p.is_active, 1)=1 THEN 'ACTIVE'
        ELSE 'INACTIVE'
    END,
    NULL,
    NULL,
    UPPER(COALESCE(NULLIF(TRIM(p.unidad), ''), 'PZA')),
    'NONE',
    CASE WHEN COALESCE(p.es_vendible, 1)=1 AND COALESCE(p.oculto,0)=0 THEN 1 ELSE 0 END,
    1,
    COALESCE(p.es_inventariable, 1),
    0,
    0,
    COALESCE(p.permite_receta, 0),
    COALESCE(p.es_paquete, 0),
    COALESCE(p.es_carnico, 0),
    0,
    COALESCE(p.es_carnico, 0),
    CASE WHEN COALESCE(p.es_carnico,0)=1 AND p.unidad_peso IS NOT NULL THEN 1 ELSE 0 END,
    0,
    COALESCE(p.es_carnico, 0),
    COALESCE(p.fecha_alta, datetime('now')),
    p.ultima_actualizacion
FROM productos p
"""


def run(conn) -> None:
    if not _table_exists(conn, "productos") or not _table_exists(conn, "products"):
        logger.info("148: productos/products ausente; backfill omitido.")
        return
    before = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    conn.execute(_BACKFILL)
    after = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    conn.commit()
    logger.info("148: backfill productos → products (%d filas nuevas).", after - before)


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


up = run

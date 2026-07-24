# migrations/deferred/legacy_pricing_drop.py
"""DEFERRED, ENV-GUARDED drop of the legacy pricing tables (PRC-8).

This is NOT registered in migrations/engine.py and never runs automatically.
Run it manually ONLY after:
  1. the canonical pricing schema is backfilled (migration 150) and is the source
     of truth for price and (via 151) cost;
  2. ``core/services/pricing_service.py`` delegates to the canonical
     ``ProductPriceQueryService`` (no reads of ``precios_lista`` / ``precios_volumen``
     / ``listas_precio`` / ``clientes_lista_precio``);
  3. the ``historial_precios`` bitácora reads have moved to ``price_change_log``.

Note: this drops ONLY the legacy price-*list* tables and the price-history trigger.
The legacy ``productos.precio`` / ``precio_compra`` / ``costo`` COLUMNS live on the
``productos`` master and are removed by the Products cutover
(``legacy_products_drop.py``, PROD-19) when it drops ``productos`` itself.

Because it destroys data with (historically) live readers, it refuses to run unless
``PRICING_ALLOW_LEGACY_DROP=1`` is set. Uses DROP IF EXISTS so a partial legacy
schema is fine.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("spj.migrations.legacy_pricing_drop")

_ENV_GUARD = "PRICING_ALLOW_LEGACY_DROP"

# Tablas legacy de listas/volumen/cliente/historial de precio (reemplazadas por el
# contexto canónico: price_list / product_price / volume_price /
# customer_price_list / price_change_log).
LEGACY_PRICING_TABLES = (
    "precios_volumen",
    "precios_lista",
    "clientes_lista_precio",
    "listas_precio",
    "historial_precios",
)

# Triggers legacy que escribían la bitácora de precios (043_price_history).
LEGACY_TRIGGERS = (
    "trg_historial_precio_venta",
    "trg_historial_precio_compra",
)


def run(conn) -> list[str]:
    if os.environ.get(_ENV_GUARD) != "1":
        raise RuntimeError(
            f"Rechazado: define {_ENV_GUARD}=1 para ejecutar el DROP destructivo "
            "del legacy de Precios (irreversible).")
    for trigger in LEGACY_TRIGGERS:
        conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")
    dropped: list[str] = []
    for table in LEGACY_PRICING_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        dropped.append(table)
    conn.commit()
    logger.warning("legacy_pricing_drop: %d tablas legacy de precio eliminadas.",
                   len(dropped))
    return dropped


up = run

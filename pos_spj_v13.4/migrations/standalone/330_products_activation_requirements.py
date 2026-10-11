# migrations/standalone/330_products_activation_requirements.py
"""PROD-22 — exigencias adicionales para activar productos (§45, «sólo endurecer»).

Sincroniza el catálogo gobernado con las nuevas definiciones
`products.require.*` (clasificación cárnica, vida útil en perecederos, perfil de
calidad en cárnicos, rango en peso variable) y `products.yield.default_tolerance_pct`.
Todas apagadas / en cero por omisión: ninguna instalación cambia hasta que se
encienden en Productos → Configuración. Idempotente.
"""

from __future__ import annotations

import logging

from backend.application.settings.catalog import sync_configuration_catalog

logger = logging.getLogger("spj.migrations.330")


def run(conn) -> None:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='configuration_definitions'"
    ).fetchone()
    if exists is None:
        logger.info("330: sin tablas de configuración; nada que sincronizar.")
        return
    count = sync_configuration_catalog(conn)
    conn.commit()
    logger.info("330: %d definiciones de configuración sincronizadas.", count)


up = run

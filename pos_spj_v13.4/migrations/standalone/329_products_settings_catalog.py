# migrations/standalone/329_products_settings_catalog.py
"""PROD-22 — parámetros de Productos en el catálogo gobernado (§45).

Registra las definiciones `products.*` (valores por omisión de la ficha y
alertas del §35/§36) llamando a `sync_configuration_catalog`, que es idempotente.
Los valores por omisión reproducen el comportamiento actual (alertas apagadas,
sin unidad preseleccionada): ninguna instalación cambia hasta que alguien los
edite en Productos → Configuración.
"""

from __future__ import annotations

import logging

from backend.application.settings.catalog import sync_configuration_catalog

logger = logging.getLogger("spj.migrations.329")


def run(conn) -> None:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='configuration_definitions'"
    ).fetchone()
    if exists is None:
        logger.info("329: sin tablas de configuración; nada que sincronizar.")
        return
    count = sync_configuration_catalog(conn)
    conn.commit()
    logger.info("329: %d definiciones de configuración sincronizadas.", count)


up = run

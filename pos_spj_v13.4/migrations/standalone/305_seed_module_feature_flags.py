"""305 — Un feature flag por módulo, para apagarlo por sucursal (2026-10-04).

Apagar un módulo en una sucursal no tenía forma de hacerse: la barra global
sabía ocultar elementos por flag, pero ningún módulo declaraba uno. Desde esta
versión cada módulo tiene su flag `modulo.<id>` (ver
`backend/application/feature_flags/module_flags.py`), ENCENDIDO por omisión:
nada cambia hasta que alguien agrega, en Configuración → Feature Flags, una
regla de ámbito SUCURSAL que lo apague.

Configuración no recibe flag: apagarla dejaría sin la pantalla para volver a
encenderla. Foto fija de los módulos del shell el día que corrió. Idempotente
(un flag que ya existe no se toca).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.305")

MODULES = (
    ("sales_pos", "Punto de Venta"), ("customers_crm", "Clientes y CRM"),
    ("finance", "Finanzas"), ("hr", "Recursos Humanos"), ("inventory", "Inventario"),
    ("products", "Productos"), ("purchasing", "Compras"), ("transfers", "Transferencias"),
    ("cash_register", "Caja"), ("business_intelligence", "Inteligencia de Negocios"),
    ("losses", "Mermas y Pérdidas"), ("meat_processing", "Producción"),
    ("orders_delivery", "Pedidos y Reparto"), ("fidelidad", "Fidelidad"),
    ("assets", "Activos"), ("pricing", "Precios y Costos"),
)


def run(conn) -> None:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ff_flags'"
                    ).fetchone() is None:
        logger.info("305: sin ff_flags; nada que sembrar.")
        return
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    creados = 0
    for module_id, nombre in MODULES:
        cur = conn.execute(
            "INSERT OR IGNORE INTO ff_flags (id, code, name, description, default_enabled, active,"
            " created_at, updated_at) VALUES (?,?,?,?,1,1,?,?)",
            (new_uuid(), f"modulo.{module_id}", f"Módulo: {nombre}",
             "Apágalo para una sucursal con una regla de ámbito Sucursal.", ahora, ahora))
        creados += max(cur.rowcount or 0, 0)
    conn.commit()
    logger.info("305: %s flags de módulo creados.", creados)


up = run

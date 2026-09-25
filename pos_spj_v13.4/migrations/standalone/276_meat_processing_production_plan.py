"""276 — Plan de producción de Procesamiento (decisión del usuario, 2026-09-25).

Un plan por sucursal y DÍA (`production_plans`, único por sucursal y fecha) con
sus líneas (`production_plan_lines`): producto demandado, proceso y producto
objetivo de la orden que lo atenderá, fuente (manual, reposición de Inventario,
pronóstico de BI), y lo ya convertido en órdenes.

El plan no mueve inventario; convertir una línea crea la orden (aprobada).
Idempotente.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.meat_processing_schema import (
    create_meat_processing_plan_schema,
)

logger = logging.getLogger("spj.migrations.276")


def run(conn) -> None:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table'"
                    " AND name='processing_orders'").fetchone() is None:
        logger.info("276: sin Procesamiento; nada que hacer.")
        return
    create_meat_processing_plan_schema(conn)
    conn.commit()
    logger.info("276: plan de producción listo.")


up = run

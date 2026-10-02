# migrations/standalone/277_purchase_order_line_units.py
"""277 — purchase_order_lines.purchase_unit / inventory_unit (Compras FASE 5).

La orden de compra sólo guardaba ``conversion_factor``, y la pantalla lo dejaba
teclear. Con las unidades definidas por Productos (FASE 3), la línea guarda en
qué unidad se ordenó y cuál es la de inventario; el factor lo deriva el caso de
uso del maestro. Líneas existentes quedan con unidades vacías (= unidad base del
producto al leerlas).

Re-ejecuta el ``create_procurement_schema`` idempotente (mismo patrón que 253).
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema

logger = logging.getLogger("spj.migrations.277")


def run(conn) -> None:
    create_procurement_schema(conn)
    conn.commit()
    logger.info("277: purchase_order_lines.purchase_unit/inventory_unit aseguradas.")


up = run

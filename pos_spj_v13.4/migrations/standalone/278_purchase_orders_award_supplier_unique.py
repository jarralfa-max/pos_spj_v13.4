# migrations/standalone/278_purchase_orders_award_supplier_unique.py
"""278 — índice único purchase_orders(source_award_id, supplier_id) (Compras FASE 6).

Una adjudicación genera una orden por proveedor. El índice parcial (sólo filas
con adjudicación) hace que reintentar "Generar órdenes" nunca duplique, aunque dos
usuarios lo intenten a la vez. Re-ejecuta el ``create_procurement_schema``
idempotente (mismo patrón que 253/277).
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema

logger = logging.getLogger("spj.migrations.278")


def run(conn) -> None:
    create_procurement_schema(conn)
    conn.commit()
    logger.info("278: índice único de orden por adjudicación y proveedor asegurado.")


up = run

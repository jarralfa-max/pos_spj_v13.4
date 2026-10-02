# migrations/standalone/279_purchase_order_enterprise_fields.py
"""279 — orden de compra completa y confirmación del proveedor (Compras FASE 7).

``purchase_orders``: tipo de cambio, fecha requerida y prometida, forma y
dirección de entrega, centro de costo, proyecto, contrato, notas, y los datos de
la CONFIRMACIÓN del proveedor (referencia, fecha, fecha de entrega confirmada,
excepciones, comentarios, quién la registró). «Enviada» ya no equivale a
«aceptada».

``purchase_order_lines``: descuento, impuesto y cantidad confirmada.

Re-ejecuta el ``create_procurement_schema`` idempotente (patrón 253/277/278).
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema

logger = logging.getLogger("spj.migrations.279")


def run(conn) -> None:
    create_procurement_schema(conn)
    conn.commit()
    logger.info("279: orden de compra enterprise + confirmación del proveedor.")


up = run

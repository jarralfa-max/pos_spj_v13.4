"""287 — Orden de compra a precio por kg (peso variable, Compras §16-17).

«5 cajas de diezmillo a $95/kg»: el precio de la línea es POR KG, la orden se
estima con el peso nominal de la presentación (5 × 25 kg) y lo que se paga sale
del PESO REAL aceptado al recibir; la factura se concilia en kg.

* ``purchase_order_lines.pricing_basis`` (``PER_KILOGRAM`` o vacío) e
  ``inventory_by_weight``, vía ``create_procurement_schema``. Las líneas
  existentes quedan por unidad, como se pactaron.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema

logger = logging.getLogger("spj.migrations.287")


def run(conn) -> None:
    create_procurement_schema(conn)
    conn.commit()
    logger.info("287: orden de compra a precio por kg.")


up = run

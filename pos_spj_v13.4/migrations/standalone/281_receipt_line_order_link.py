# migrations/standalone/281_receipt_line_order_link.py
"""281 — La línea de recepción sabe a qué línea de la orden corresponde (Compras FASE 14).

La conciliación de tres vías compara factura ↔ recepción ↔ orden LÍNEA POR
LÍNEA. La recepción agrupaba por producto: con dos líneas del mismo producto en
una orden, cada línea tomaba el total recibido del producto y la conciliación
dejaba pasar una sobrefacturación. La FASE 11 agregó el vínculo a la entidad,
pero la tabla no tenía la columna y el dato se perdía al guardar.

* ``goods_receipt_lines.purchase_order_line_id`` (vía ``create_procurement_schema``).
* Relleno: las recepciones previas se ligan cuando la orden tiene UNA sola línea
  de ese producto (sin ambigüedad). Las demás se quedan sin vínculo y la
  conciliación las reparte por producto, línea por línea, hasta lo pedido.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema

logger = logging.getLogger("spj.migrations.281")


def run(conn) -> None:
    create_procurement_schema(conn)
    cursor = conn.execute(
        "UPDATE goods_receipt_lines SET purchase_order_line_id = ("
        " SELECT l.id FROM purchase_order_lines l"
        " JOIN goods_receipts g ON g.purchase_order_id = l.purchase_order_id"
        " WHERE g.id = goods_receipt_lines.goods_receipt_id"
        " AND l.product_id = goods_receipt_lines.product_id)"
        " WHERE purchase_order_line_id IS NULL AND ("
        " SELECT COUNT(*) FROM purchase_order_lines l"
        " JOIN goods_receipts g ON g.purchase_order_id = l.purchase_order_id"
        " WHERE g.id = goods_receipt_lines.goods_receipt_id"
        " AND l.product_id = goods_receipt_lines.product_id) = 1")
    conn.commit()
    logger.info("281: %s líneas de recepción ligadas a su línea de orden.",
                cursor.rowcount if cursor.rowcount is not None else 0)


up = run

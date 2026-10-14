"""334 — Auditoría directa de Compras (d9f2bca), 2026-10-11.

Lleva el esquema de Compras al contrato de las correcciones de la auditoría
(ver docs/refactor/PUR-AUD_auditoria_d9f2bca.md):

* ``supplier_invoice_lines.purchase_nature`` (C04): la naturaleza de cada línea
  de factura se guarda; se rehidrataba como INVENTORY y un activo terminaba
  reconocido como inventario.
* ``goods_receipt_lines.direct_purchase_line_id`` (C10): la recepción de una
  compra directa sabe qué línea cubre, para recibir por partes.

Usa el esquema canónico (``create_procurement_schema``), cuyos ``ALTER`` están
protegidos con ``PRAGMA table_info``. Sólo agrega columnas. Idempotente.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema

logger = logging.getLogger("spj.migrations.334")


def run(conn) -> None:
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table'"
                        " AND name='purchase_orders'").fetchone():
        logger.info("334: sin esquema de Compras; nada que actualizar.")
        return
    create_procurement_schema(conn)
    conn.commit()
    logger.info("334: esquema de Compras al contrato de la auditoría d9f2bca.")


up = run

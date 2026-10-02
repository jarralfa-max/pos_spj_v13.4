"""285 — Forma de surtido de la compra rápida (Compras §11).

La compra rápida sólo distinguía «con recepción inmediata / pendiente», mezclado
en el mismo combo que «Servicio» y «Gasto». El §11 pide no confundir la
condición comercial con la forma LOGÍSTICA de recibir: recepción inmediata,
posterior, entrega del proveedor o recolección en proveedor (ésta con la bodega
de origen, como la orden de compra).

* ``direct_purchases.fulfillment_mode`` / ``origin_supplier_address_id`` /
  ``origin_address_snapshot`` (vía ``create_procurement_schema``).
* Relleno: inmediata → ``IMMEDIATE_RECEIPT``; pendiente → ``LATER_RECEIPT``;
  servicios y gastos quedan sin surtido.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema

logger = logging.getLogger("spj.migrations.285")


def run(conn) -> None:
    create_procurement_schema(conn)
    conn.execute("UPDATE direct_purchases SET fulfillment_mode='IMMEDIATE_RECEIPT'"
                 " WHERE COALESCE(fulfillment_mode,'')=''"
                 " AND mode='DIRECT_WITH_IMMEDIATE_RECEIPT'")
    conn.execute("UPDATE direct_purchases SET fulfillment_mode='LATER_RECEIPT'"
                 " WHERE COALESCE(fulfillment_mode,'')=''"
                 " AND mode='DIRECT_WITH_PENDING_RECEIPT'")
    conn.commit()
    logger.info("285: forma de surtido en la compra rápida.")


up = run

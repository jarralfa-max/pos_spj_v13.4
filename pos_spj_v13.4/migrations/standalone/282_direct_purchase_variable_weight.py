# migrations/standalone/282_direct_purchase_variable_weight.py
"""282 — Peso variable en la compra rápida (Compras FASE 16, §17 y §41 prueba 2).

«Diezmillo de res, 5 cajas, 127.850 kg pesados a $95/kg»: Productos ya define el
peso variable (``catch_weight_enabled`` + ``product_catch_weight_config.price_basis``),
pero la compra sólo sabía cobrar cantidad × costo con el factor nominal de la
caja. La línea guarda ahora:

* ``net_weight``: lo que pesó la báscula al comprar;
* ``pricing_basis``: ``PER_KILOGRAM`` cuando el importe es peso × costo por kg;
* ``inventory_by_weight``: la unidad de inventario es de peso, así que entra el
  peso de báscula y no 5 × 25 kg nominales.

Columnas vía ``create_procurement_schema`` (mismo mecanismo de ALTER idempotente).
Las líneas existentes quedan como estaban (sin peso, base vacía).
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema

logger = logging.getLogger("spj.migrations.282")


def run(conn) -> None:
    create_procurement_schema(conn)
    conn.commit()
    logger.info("282: peso variable en las líneas de compra rápida.")


up = run

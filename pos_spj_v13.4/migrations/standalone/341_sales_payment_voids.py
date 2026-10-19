"""341 — pagos anulados en el cobro (auditoría de Ventas cebf67a, V02/V03, 2026-10-15).

`sale_payment_voids`: el rastro de cada pago que se anuló mientras la venta
seguía en cobro — al cancelar una venta con pagos (decisión del usuario:
"compensar y avisar") o al quitar un pago ya registrado desde el cobro. Antes
cancelar dejaba los pagos colgados de una venta CANCELLED y la deuda a crédito
viva en CxC.

Sólo crea la tabla (vía el esquema canónico de Ventas). Idempotente.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.341")


def run(conn) -> None:
    from backend.infrastructure.db.schema.sales_schema import create_sales_schema

    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sales'"
                    ).fetchone() is None:
        logger.info("341: base sin Ventas canónicas; nada que crear.")
        return
    create_sales_schema(conn)
    conn.commit()
    logger.info("341: sale_payment_voids lista.")

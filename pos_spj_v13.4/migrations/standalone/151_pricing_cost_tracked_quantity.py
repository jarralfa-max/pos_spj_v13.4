# migrations/standalone/151_pricing_cost_tracked_quantity.py
"""PRC-6 — base de cantidad para el costo promedio móvil.

Agrega ``product_cost.tracked_quantity`` (TEXT Decimal): la cantidad acumulada
que Pricing usa para recalcular el costo promedio ponderado cuando llega una
recepción de compra o un costeo de producción. Es interno de Costing (Pricing es
dueño de su propia base de costo; no depende de la cantidad on-hand de Inventory).

Idempotente: sólo agrega la columna si falta. Sin REAL.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.151")


def run(conn) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(product_cost)").fetchall()}
    if not cols:
        logger.info("151: product_cost ausente; se omite (149 lo crea).")
        return
    if "tracked_quantity" not in cols:
        conn.execute("ALTER TABLE product_cost ADD COLUMN tracked_quantity TEXT")
        logger.info("151: product_cost.tracked_quantity agregada.")
    conn.commit()


up = run

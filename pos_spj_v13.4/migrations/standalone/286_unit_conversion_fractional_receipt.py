"""286 — Política de recepción fraccionada por presentación (Compras §27).

«OC: 5 costales de 25 kg; recibido: 4 costales completos + 22 kg». Si eso se
acepta o no lo decide el PRODUCTO/PRESENTACIÓN, nunca un `if` en Compras.

* ``product_unit_conversions.allow_fractional_receipt`` (1 = se puede recibir en
  fracción). Por omisión 1: es el comportamiento que existía (cualquier decimal),
  así que ninguna recepción en curso cambia. Se ajusta por presentación en
  Productos → Unidades de compra.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.286")


def run(conn) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(product_unit_conversions)")}
    if columns and "allow_fractional_receipt" not in columns:
        conn.execute("ALTER TABLE product_unit_conversions ADD COLUMN"
                     " allow_fractional_receipt INTEGER NOT NULL DEFAULT 1")
    conn.commit()
    logger.info("286: política de recepción fraccionada por presentación.")


up = run

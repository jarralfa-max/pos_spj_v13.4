"""384 — referencia de pago única entre ventas (SDLC-PAY-002, 2026-11-06).

Un pago de Mercado Pago, Tarjeta o Transferencia no anulado sólo puede aparecer
una vez en `sale_payments`. Índice único parcial sobre método + referencia
normalizada: sin referencia no participa, y anular un pago lo saca de la tabla.

Medido en una copia de la base real: 0 pagos, ninguna referencia vacía o
repetida. Si otra instalación trae duplicados, no se tocan (son rastro
financiero): el índice protege desde el último duplicado en adelante, se avisa
en el log y el caso de uso sigue revisando todo el historial. Idempotente.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.384")


def run(conn) -> None:
    from backend.infrastructure.db.schema.sales_schema import create_payment_reference_index

    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sale_payments'"
                    ).fetchone() is None:
        logger.info("384: base sin Ventas canónicas; nada que crear.")
        return
    repetidas = conn.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM sale_payments"
        " WHERE method IN ('MERCADO_PAGO','CARD','TRANSFER')"
        " AND reference IS NOT NULL AND TRIM(reference) <> ''"
        " GROUP BY method, UPPER(TRIM(reference)) HAVING COUNT(*) > 1)").fetchone()[0]
    corte = None
    if repetidas:
        corte = conn.execute("SELECT MAX(captured_at) FROM sale_payments").fetchone()[0]
        logger.warning("384: %d referencias repetidas en el historial; se conservan y el "
                       "índice protege lo capturado después de %s.", repetidas, corte)
    create_payment_reference_index(conn, captured_after=corte)
    conn.commit()
    logger.info("384: referencia de pago única lista.")


up = run

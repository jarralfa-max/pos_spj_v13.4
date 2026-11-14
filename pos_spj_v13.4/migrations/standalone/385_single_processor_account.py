"""385 — una sola cuenta de procesadores (SDLC-PAY-004, 2026-11-06).

Decisión del responsable: una cuenta de tesorería para Mercado Pago y tarjetas,
con espejo en la 1115; la venta carga directo a ella. El cambio de fondo está en
los manejadores de Finanzas; aquí sólo se renombra la cuenta sembrada, que decía
«Procesador de tarjetas» y ahora también recibe Mercado Pago.

La 1120 no se reclasifica: decisión del responsable («no hay datos») y medido en
una copia de la base real, 0 renglones contables. Si otra instalación los
tuviera, se avisa en el log y no se mueve nada. Idempotente.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger("spj.migrations.385")

NOMBRE_ANTERIOR = "Procesador de tarjetas"
NOMBRE = "Procesadores de pago (Mercado Pago y tarjetas)"


def run(conn) -> None:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='treasury_accounts'"
                    ).fetchone() is None:
        logger.info("385: base sin Finanzas; nada que hacer.")
        return
    conn.execute(
        "UPDATE treasury_accounts SET name=?, updated_at=?"
        " WHERE account_type='PAYMENT_PROCESSOR' AND name=?",
        (NOMBRE, datetime.now(timezone.utc).isoformat(timespec="seconds"), NOMBRE_ANTERIOR))
    pendientes = conn.execute(
        "SELECT COUNT(*) FROM journal_lines l JOIN accounts a ON a.id=l.account_id"
        " WHERE a.code='1120'").fetchone()[0]
    if pendientes:
        logger.warning("385: la 1120 tiene %d renglones; no se reclasifican.", pendientes)
    conn.commit()


up = run

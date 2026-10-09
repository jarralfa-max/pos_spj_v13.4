"""316 — recupera la proyección de compras de los clientes (§49).

POR QUÉ (medido en una copia de la base viva el 2026-10-08): la proyección
Ventas → Clientes se suscribía en ``core/events/wiring.py``, borrado con la
shell legacy. Las ventas completadas con cliente se despacharon del outbox de
Ventas sin que nadie las contara: el expediente marca 0 compras y la etapa
del cliente nunca avanza. CRM-43 vuelve a suscribirla
(``customers/integrations/sales_wiring.py``); esta migración aplica, UNA vez,
los ``SALE_COMPLETED``/``SALE_REVERSED`` ya despachados.

Idempotente: usa el mismo ``event_id`` que el suscriptor, y el caso de uso
ignora un evento ya procesado (``customer_processed_events``).
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("spj.migrations.316")


def _tabla(conn, nombre: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (nombre,)).fetchone() is not None


def run(conn) -> None:
    if not all(_tabla(conn, t) for t in ("sales_outbox", "customers",
                                         "customer_processed_events")):
        logger.info("316: faltan tablas; nada que recuperar.")
        return
    from backend.application.customers.integrations.sales_wiring import (
        on_sale_completed,
        on_sale_reversed,
    )
    aplicados = 0
    filas = conn.execute(
        "SELECT event_name, payload_json FROM sales_outbox"
        " WHERE event_name IN ('SALE_COMPLETED','SALE_REVERSED') ORDER BY created_at").fetchall()
    for nombre, payload_json in filas:
        try:
            sobre = json.loads(payload_json)
        except (TypeError, ValueError):
            continue
        manejador = on_sale_completed if nombre == "SALE_COMPLETED" else on_sale_reversed
        if manejador(conn, sobre):
            aplicados += 1
    conn.commit()
    logger.info("316: %s eventos de venta aplicados al expediente.", aplicados)


up = run

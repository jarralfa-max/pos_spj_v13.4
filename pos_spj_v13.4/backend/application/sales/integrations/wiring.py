"""Raíz de composición de las integraciones de Ventas (Fase 6, 2026-09-18).

MEDIDO: `SaleCompletedHandler` (ingreso, IVA, descuento, efectivo/tarjeta/
crédito, CxC y costo de venta) estaba completo y NADIE lo registraba, y
`sales_outbox` no tenía despachador: una venta completada no llegaba nunca a
contabilidad. `wire_sales` lo suscribe; `dispatch_sales_outbox` entrega lo
pendiente.
"""

from __future__ import annotations

import json
import logging

from backend.application.sales.integrations.finance_translator import (
    sale_completed_to_finance,
)

logger = logging.getLogger("spj.sales.wiring")

SALE_COMPLETED = "SALE_COMPLETED"

#: Eventos con impacto financiero: sin un consumidor que los atienda NO se
#: marcan despachados. Si el cableado de arranque fallara, el bus los
#: entregaría a nadie y la venta no llegaría nunca a contabilidad.
REQUIRES_CONSUMER = frozenset({SALE_COMPLETED})


def wire_sales(bus, connection) -> dict:
    from backend.application.event_handlers.finance.sale_completed_handler import (
        SaleCompletedHandler,
    )
    finanzas = SaleCompletedHandler(connection)

    def _a_finanzas(envelope: dict) -> None:
        finanzas.handle(sale_completed_to_finance(envelope))

    subscribe = getattr(bus, "subscribe", None)
    if subscribe is None:
        raise RuntimeError("El bus no expone subscribe()")
    try:
        subscribe(SALE_COMPLETED, _a_finanzas, priority=50, label="sales_finance")
    except TypeError:
        subscribe(SALE_COMPLETED, _a_finanzas)
    return {"subscribed": [f"out:{SALE_COMPLETED}->finance"], "count": 1}


def dispatch_sales_outbox(connection, bus, *, limit: int = 500) -> dict:
    """Publica los eventos PENDIENTES de `sales_outbox`, en orden.

    Estricto: si un suscriptor falla, el evento queda PENDIENTE y se reintenta
    en el siguiente despacho (los manejadores de Finanzas son idempotentes por
    `event_id`). El bus en modo normal traga el error y el evento se marcaría
    despachado sin haber llegado a contabilidad.
    """
    from backend.infrastructure.db.repositories.sales.outbox_repository import (
        SalesOutboxRepository,
    )
    outbox = SalesOutboxRepository(connection)
    pendientes = outbox.list_pending(limit=limit)
    despachados = fallidos = sin_consumidor = 0
    for fila in pendientes:
        try:
            sobre = json.loads(fila["payload_json"])
            if not isinstance(sobre, dict):
                raise ValueError("el payload del outbox debe ser un objeto JSON")
            atendidos = bus.publish(fila["event_name"], sobre, strict=True)
            if fila["event_name"] in REQUIRES_CONSUMER and not atendidos:
                sin_consumidor += 1
                logger.error("sales outbox: %s sin consumidor; queda pendiente",
                             fila["event_name"])
                continue
            outbox.mark_dispatched(fila["id"])
            # Uno a uno: si el siguiente falla y su manejador revierte la
            # conexión, no se lleva de paso lo ya despachado.
            connection.commit()
            despachados += 1
        except Exception:
            fallidos += 1
            logger.exception("sales outbox: no se pudo despachar %s (%s)",
                             fila.get("id"), fila.get("event_name"))
    return {"pending": len(pendientes), "dispatched": despachados, "failed": fallidos,
            "without_consumer": sin_consumidor}

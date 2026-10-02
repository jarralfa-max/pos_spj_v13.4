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
    sale_returned_to_finance,
    sale_reversed_to_finance,
)

logger = logging.getLogger("spj.sales.wiring")

SALE_COMPLETED = "SALE_COMPLETED"
SALE_RETURNED = "SALE_RETURNED"
SALE_REVERSED = "SALE_REVERSED"
SALE_CANCELLED = "SALE_CANCELLED"

#: Eventos con impacto financiero o de puntos: sin un consumidor que los
#: atienda NO se marcan despachados. Si el cableado de arranque fallara, el bus
#: los entregaría a nadie y la venta no llegaría nunca a contabilidad (ni el
#: canje de una venta cancelada volvería al cliente).
REQUIRES_CONSUMER = frozenset({SALE_COMPLETED, SALE_RETURNED, SALE_REVERSED, SALE_CANCELLED})


def wire_sales(bus, connection) -> dict:
    """Suscribe los consumidores de Finanzas de la venta, su devolución parcial
    y su reverso. Hasta el 2026-10-02 sólo había el de la venta: una devolución
    no tocaba la contabilidad y `SaleReversedHandler` existía sin suscriptor."""
    from backend.application.event_handlers.finance.sale_completed_handler import (
        SaleCompletedHandler,
    )
    from backend.application.event_handlers.finance.sale_returned_handler import (
        SaleReturnedHandler,
    )
    from backend.application.event_handlers.finance.sale_reversed_handler import (
        SaleReversedHandler,
    )
    consumidores = (
        (SALE_COMPLETED, SaleCompletedHandler(connection), sale_completed_to_finance),
        (SALE_RETURNED, SaleReturnedHandler(connection), sale_returned_to_finance),
        (SALE_REVERSED, SaleReversedHandler(connection), sale_reversed_to_finance),
    )

    from backend.application.loyalty.integrations.sales_events import SaleLoyaltyEventHandlers

    fidelidad = SaleLoyaltyEventHandlers(connection)
    # Puntos por compra (2026-10-02): Fidelidad acredita al completar y retira
    # al devolver/reversar. Prioridad menor que Finanzas (§EventBus: 10).
    puntos = (
        (SALE_COMPLETED, fidelidad.on_sale_completed),
        (SALE_RETURNED, fidelidad.on_sale_returned),
        (SALE_REVERSED, fidelidad.on_sale_reversed),
        # El canje se descuenta antes de cobrar: cancelar lo devuelve.
        (SALE_CANCELLED, fidelidad.on_sale_cancelled),
    )

    subscribe = getattr(bus, "subscribe", None)
    if subscribe is None:
        raise RuntimeError("El bus no expone subscribe()")
    suscritos = []
    for evento, manejador in puntos:
        try:
            subscribe(evento, manejador, priority=10, label=f"sales_loyalty_{evento.lower()}")
        except TypeError:
            subscribe(evento, manejador)
        suscritos.append(f"out:{evento}->loyalty")
    for evento, manejador, traducir in consumidores:
        def _a_finanzas(envelope: dict, _m=manejador, _t=traducir) -> None:
            _m.handle(_t(envelope))
        try:
            subscribe(evento, _a_finanzas, priority=50, label=f"sales_finance_{evento.lower()}")
        except TypeError:
            subscribe(evento, _a_finanzas)
        suscritos.append(f"out:{evento}->finance")
    return {"subscribed": suscritos, "count": len(suscritos)}


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

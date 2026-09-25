"""Raíz de composición de las integraciones de Costos.

`wire_costing` suscribe a Finanzas al hecho `PROCESSING_COST_ALLOCATED`: antes
existía `ProductionCompletedHandler` (asiento de producción y merma) y NADIE
publicaba su evento, así que ninguna producción llegaba a contabilidad.

`PRODUCTION_OUTPUT_COSTED` no se suscribe aquí: Precios ya lo escucha
(`wire_pricing` → `ProductCostProjectionHandler`).

`dispatch_costing_outbox` entrega lo pendiente. Estricto, como Ventas: un hecho
con impacto financiero o de costo que nadie atendió NO se marca despachado.
"""

from __future__ import annotations

import json
import logging

from backend.application.costing.processing_costing import (
    PROCESSING_COST_ALLOCATED,
    PRODUCTION_OUTPUT_COSTED,
)

logger = logging.getLogger("spj.costing.wiring")

REQUIRES_CONSUMER = frozenset({PROCESSING_COST_ALLOCATED, PRODUCTION_OUTPUT_COSTED})


def wire_costing(bus, connection) -> dict:
    from backend.application.event_handlers.finance.inventory_adjustment_handler import (
        ProductionCompletedHandler,
    )
    finanzas = ProductionCompletedHandler(connection)
    subscribe = getattr(bus, "subscribe", None)
    if subscribe is None:
        raise RuntimeError("El bus no expone subscribe()")
    try:
        subscribe(PROCESSING_COST_ALLOCATED, finanzas.handle, priority=50,
                  label="costing_production_finance")
    except TypeError:
        subscribe(PROCESSING_COST_ALLOCATED, finanzas.handle)
    return {"subscribed": [f"out:{PROCESSING_COST_ALLOCATED}->finance"], "count": 1}


def dispatch_costing_outbox(connection, bus, *, limit: int = 500) -> dict:
    from backend.infrastructure.db.repositories.costing.processing_cost_repository import (
        CostingOutboxRepository,
    )
    outbox = CostingOutboxRepository(connection)
    pendientes = outbox.list_pending(limit=limit)
    despachados = fallidos = sin_consumidor = 0
    for fila in pendientes:
        try:
            sobre = json.loads(fila["payload_json"])
            atendidos = bus.publish(fila["event_name"], sobre, strict=True)
            if fila["event_name"] in REQUIRES_CONSUMER and not atendidos:
                sin_consumidor += 1
                outbox.mark_failed(fila["id"], "sin consumidor")
                connection.commit()
                logger.error("costing outbox: %s sin consumidor; queda pendiente",
                             fila["event_name"])
                continue
            outbox.mark_dispatched(fila["id"])
            connection.commit()
            despachados += 1
        except Exception as exc:  # noqa: BLE001 — queda pendiente para reintento
            fallidos += 1
            rollback = getattr(connection, "rollback", None)
            if rollback is not None:
                rollback()
            outbox.mark_failed(fila["id"], str(exc))
            connection.commit()
            logger.exception("costing outbox: no se pudo despachar %s", fila["event_name"])
    return {"pending": len(pendientes), "dispatched": despachados, "failed": fallidos,
            "without_consumer": sin_consumidor}

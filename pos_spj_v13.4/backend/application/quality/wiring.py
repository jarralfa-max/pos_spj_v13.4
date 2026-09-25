"""Raíz de composición de las integraciones de Calidad.

`wire_quality` suscribe a Procesamiento a las decisiones de Calidad;
`dispatch_quality_outbox` las entrega, estricto: una decisión que nadie
atendió queda pendiente para reintento.
"""

from __future__ import annotations

import json
import logging

from backend.application.quality.output_inspection import QUALITY_DECISION_EVENTS

logger = logging.getLogger("spj.quality.wiring")


def wire_quality(bus, connection) -> dict:
    from backend.application.event_handlers.meat_processing.quality_decision_handler import (
        QualityDecisionRecordedHandler,
    )
    manejador = QualityDecisionRecordedHandler(connection)
    for evento in sorted(QUALITY_DECISION_EVENTS):
        try:
            bus.subscribe(evento, manejador.handle, priority=80,
                          label=f"meat_processing_{evento.lower()}")
        except TypeError:
            bus.subscribe(evento, manejador.handle)
    return {"subscribed": [f"out:{e}->meat_processing" for e in sorted(QUALITY_DECISION_EVENTS)],
            "count": len(QUALITY_DECISION_EVENTS)}


def dispatch_quality_outbox(connection, bus, *, limit: int = 500) -> dict:
    from backend.infrastructure.db.repositories.quality.inspection_repository import (
        QualityOutboxRepository,
    )
    outbox = QualityOutboxRepository(connection)
    pendientes = outbox.list_pending(limit=limit)
    despachados = fallidos = 0
    for fila in pendientes:
        try:
            atendidos = bus.publish(fila["event_name"], json.loads(fila["payload_json"]),
                                    strict=True)
            if not atendidos:
                outbox.mark_failed(fila["id"], "sin consumidor")
                connection.commit()
                continue
            outbox.mark_dispatched(fila["id"])
            connection.commit()
            despachados += 1
        except Exception as exc:  # noqa: BLE001 — queda pendiente
            fallidos += 1
            rollback = getattr(connection, "rollback", None)
            if rollback is not None:
                rollback()
            outbox.mark_failed(fila["id"], str(exc))
            connection.commit()
            logger.exception("quality outbox: no se pudo despachar %s", fila["event_name"])
    return {"pending": len(pendientes), "dispatched": despachados, "failed": fallidos}

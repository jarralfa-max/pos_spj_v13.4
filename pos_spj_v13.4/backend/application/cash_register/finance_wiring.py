"""Caja → Finanzas: suscripción y despacho del `cash_outbox` (CASH-26, bloque 2).

MEDIDO 2026-10-07: cada operación de Caja deja su evento en `cash_outbox`
dentro de la misma transacción, pero NADIE lo despachaba: el único lector era
el envío fuera de línea (sin transporte real). `CashFinanceEventRouter` y
`CashShiftClosedHandler` estaban escritos y probados sin suscriptor, así que un
Corte Z nunca llegaba a contabilidad. Mismo modelo que Ventas
(`backend/application/sales/integrations/wiring.py`): `wire_cash_register`
suscribe y `dispatch_cash_outbox` entrega lo pendiente después de cada
operación de Caja.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("spj.cash_register.finance_wiring")

#: Eventos con efecto o rastro contable: sin consumidor NO se marcan
#: despachados (un arranque sin cableado no debe perder el Corte Z).
REQUIRES_CONSUMER = frozenset({
    "CASH_Z_CUT_GENERATED",
    "CASH_DIFFERENCE_DETECTED",
    "CASH_REFUND_PROCESSED",
    "CASH_HANDOVER_RECEIVED",
    "CASH_DEPOSIT_PREPARED",
})

#: Tras tantos intentos fallidos el evento pasa a DEAD_LETTER: sigue visible y
#: con su último error, pero deja de reintentarse en cada operación.
MAX_ATTEMPTS = 10


def wire_cash_register(bus, connection) -> dict:
    """Suscribe a Finanzas los eventos de Caja que ella sabe atender."""
    from backend.application.event_handlers.finance.cash_finance_router import (
        CashFinanceEventRouter,
    )

    router = CashFinanceEventRouter(connection)
    subscribe = getattr(bus, "subscribe", None)
    if subscribe is None:
        raise RuntimeError("El bus no expone subscribe()")
    suscritos = []
    for evento in sorted(REQUIRES_CONSUMER):
        try:
            subscribe(evento, router.handle, priority=50,
                      label=f"cash_finance_{evento.lower()}")
        except TypeError:
            subscribe(evento, router.handle)
        suscritos.append(f"{evento}->finance")
    return {"subscribed": suscritos, "count": len(suscritos)}


def dispatch_cash_outbox(connection, bus, *, limit: int = 500) -> dict:
    """Publica en orden los eventos PENDIENTES de `cash_outbox`.

    Estricto: si Finanzas falla, el evento queda PENDIENTE con su error y se
    reintenta en el siguiente despacho (los manejadores son idempotentes por
    `event_id`). Uno a uno con su propio commit: un fallo no se lleva lo ya
    despachado.
    """
    from backend.infrastructure.db.repositories.cash_register.repositories import (
        CashOutboxRepository,
    )

    outbox = CashOutboxRepository(connection)
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
                logger.error("cash outbox: %s sin consumidor; queda pendiente",
                             fila["event_name"])
                continue
            outbox.mark_dispatched(fila["id"], now=_now())
            connection.commit()
            despachados += 1
        except Exception as exc:  # noqa: BLE001 - se registra y se reintenta
            fallidos += 1
            logger.exception("cash outbox: no se pudo despachar %s (%s)",
                             fila["id"], fila["event_name"])
            try:
                connection.rollback()
                outbox.mark_attempt_failed(
                    fila["id"], error=f"{type(exc).__name__}: {exc}",
                    dead=int(fila["attempt_count"]) + 1 >= MAX_ATTEMPTS)
                connection.commit()
            except Exception:  # noqa: BLE001
                logger.exception("cash outbox: no se pudo registrar el fallo de %s", fila["id"])
    return {"pending": len(pendientes), "dispatched": despachados, "failed": fallidos,
            "without_consumer": sin_consumidor}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

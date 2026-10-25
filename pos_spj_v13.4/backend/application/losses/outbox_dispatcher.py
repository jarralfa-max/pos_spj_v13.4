"""Despachador del ``loss_outbox`` (FIN-ERP, 2026-10-22).

Mermas encolaba sus hechos (valuación, solicitud de reconocimiento contable…)
en ``loss_outbox`` dentro de la misma transacción, pero nada los entregaba: la
merma valuada nunca llegaba al mayor. Aquí se publican en orden en el bus.

``LOSS_FINANCE_RECOGNITION_REQUESTED`` EXIGE consumidor (Finanzas): publicado
sin suscriptor queda FALLIDO y visible, no se da por entregado. Tras
``MAX_ATTEMPTS`` intentos pasa a DEAD_LETTER con su último error.
"""

from __future__ import annotations

import json
import logging

from backend.domain.losses.events import LossEvents

logger = logging.getLogger("spj.losses.outbox_dispatcher")

REQUIRES_CONSUMER = frozenset({LossEvents.LOSS_FINANCE_RECOGNITION_REQUESTED})
MAX_ATTEMPTS = 10


def dispatch_loss_outbox(repository, bus, *, limit: int = 200) -> dict:
    """``repository``: ``LossOutboxRepository`` (o equivalente) sobre la base viva."""
    rows = repository.deliverable(max_attempts=MAX_ATTEMPTS, limit=limit)
    dispatched = failed = 0
    for row in rows:
        try:
            handled = bus.publish(row["event_name"], json.loads(row["payload_json"]),
                                  strict=True)
            if row["event_name"] in REQUIRES_CONSUMER and not handled:
                raise LookupError("sin consumidor registrado")
        except Exception as exc:  # queda FALLIDO y visible para reintento
            failed += 1
            logger.exception("loss_outbox: no se pudo despachar %s (%s)", row["id"],
                             row["event_name"])
            repository.mark_failed(row["id"], f"{type(exc).__name__}: {exc}",
                                   dead=row["attempts"] + 1 >= MAX_ATTEMPTS)
            continue
        repository.mark_dispatched(row["id"])
        dispatched += 1
    return {"pending": len(rows), "dispatched": dispatched, "failed": failed}

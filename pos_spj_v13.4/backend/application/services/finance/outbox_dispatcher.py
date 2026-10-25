"""Despachador del ``finance_outbox`` (auditoría d9f2bca F21, §27).

Finanzas encola sus hechos (JOURNAL_ENTRY_POSTED, COLLECTION_REGISTERED,
SUPPLIER_PAYMENT_EXECUTED…) en la misma transacción que los produce; aquí se
publican en orden en el bus de la aplicación. Cada entrega se confirma en su
propia unidad de trabajo: un fallo deja el evento PENDIENTE con ``attempts`` y
``last_error`` visibles y se reintenta hasta ``MAX_ATTEMPTS``.

Ningún hecho financiero exige consumidor HOY (Finanzas es el destino final de
los hechos operativos), así que publicarlo sin suscriptor lo da por entregado;
``REQUIRES_CONSUMER`` lista los que, sin suscriptor, deben quedar pendientes.
"""

from __future__ import annotations

import json
import logging

from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork

logger = logging.getLogger("spj.finance.outbox_dispatcher")

REQUIRES_CONSUMER: frozenset[str] = frozenset()
MAX_ATTEMPTS = 10


class MissingConsumerError(RuntimeError):
    """Un hecho que exige consumidor se publicó sin suscriptor."""


def dispatch_finance_outbox(connection, bus, *, limit: int = 500) -> dict:
    with FinanceUnitOfWork(connection) as uow:
        rows = uow.outbox.list_deliverable(max_attempts=MAX_ATTEMPTS, limit=limit)
    dispatched = failed = 0
    for row in rows:
        try:
            handled = bus.publish(row["event_name"], json.loads(row["payload_json"]),
                                  strict=True)
            if row["event_name"] in REQUIRES_CONSUMER and not handled:
                raise MissingConsumerError("sin consumidor registrado")
        except Exception as exc:  # el suscriptor falló: queda pendiente y visible
            failed += 1
            logger.exception("finance outbox: no se pudo despachar %s (%s)", row["id"],
                             row["event_name"])
            with FinanceUnitOfWork(connection) as uow:
                uow.outbox.mark_failed(row["id"], f"{type(exc).__name__}: {exc}")
            continue
        with FinanceUnitOfWork(connection) as uow:
            uow.outbox.mark_dispatched(row["id"])
        dispatched += 1
    return {"pending": len(rows), "dispatched": dispatched, "failed": failed}

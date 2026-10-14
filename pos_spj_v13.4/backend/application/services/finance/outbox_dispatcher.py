"""Despachador del ``finance_outbox`` (auditoría d9f2bca F21).

Finanzas encolaba sus hechos (JOURNAL_ENTRY_POSTED, COLLECTION_REGISTERED,
SUPPLIER_PAYMENT_EXECUTED…) en ``finance_outbox`` dentro de la misma
transacción, pero nada los leía: un consumidor futuro (BI, notificaciones) no
habría recibido nada y nadie lo habría notado. Aquí se publican en orden en el
bus de la aplicación. Ninguno exige consumidor HOY (Finanzas es el destino
final de los hechos operativos, no el origen de efectos en otros módulos), así
que publicarlos sin suscriptor los marca despachados; un fallo de un suscriptor
deja el evento PENDIENTE con ``attempts`` y ``last_error`` visibles y se
reintenta hasta ``MAX_ATTEMPTS``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("spj.finance.outbox_dispatcher")

#: Hechos financieros que, si se publican sin suscriptor, NO deben darse por
#: entregados. Vacío a propósito: hoy ningún módulo depende de ellos.
REQUIRES_CONSUMER: frozenset[str] = frozenset()
MAX_ATTEMPTS = 10


def dispatch_finance_outbox(connection, bus, *, limit: int = 500) -> dict:
    columns = {str(r[1]) for r in connection.execute("PRAGMA table_info(finance_outbox)")}
    if not columns:
        return {"pending": 0, "dispatched": 0, "failed": 0}
    tracks = "attempts" in columns
    where = "status='PENDING'" + (f" AND attempts < {MAX_ATTEMPTS}" if tracks else "")
    rows = connection.execute(
        f"SELECT id, event_name, payload_json FROM finance_outbox WHERE {where}"
        " ORDER BY created_at LIMIT ?", (limit,)).fetchall()
    dispatched = failed = 0
    for outbox_id, event_name, payload_json in rows:
        try:
            payload = json.loads(payload_json)
            handled = bus.publish(event_name, payload, strict=True)
            if event_name in REQUIRES_CONSUMER and not handled:
                raise RuntimeError("sin consumidor registrado")
            connection.execute(
                "UPDATE finance_outbox SET status='DISPATCHED', dispatched_at=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), outbox_id))
            connection.commit()
            dispatched += 1
        except Exception as exc:
            failed += 1
            logger.exception("finance outbox: no se pudo despachar %s (%s)", outbox_id,
                             event_name)
            try:
                connection.rollback()
            except Exception:
                pass
            if tracks:
                connection.execute(
                    "UPDATE finance_outbox SET attempts = attempts + 1, last_error=? WHERE id=?",
                    (str(exc)[:500], outbox_id))
                connection.commit()
    return {"pending": len(rows), "dispatched": dispatched, "failed": failed}

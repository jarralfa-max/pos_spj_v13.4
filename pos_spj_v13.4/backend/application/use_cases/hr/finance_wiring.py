"""RR. HH. → Finanzas: suscripción y despacho del ``hr_outbox`` (auditoría F21).

MEDIDO 2026-10-10: ``PayPayrollRunUseCase`` encolaba PAYROLL_PAID en
``hr_outbox`` y ``PayrollPaidHandler`` existía y pasaba sus pruebas llamado a
mano, pero nadie lo suscribía ni despachaba el outbox: una nómina pagada no
llegaba al mayor por la ruta de producción. Mismo modelo que Caja
(``cash_register/finance_wiring.py``): ``wire_hr_finance`` suscribe y
``dispatch_hr_outbox`` entrega lo pendiente después de pagar y al arrancar.

Entrega observable: si Finanzas falla, el evento queda PENDIENTE con
``attempts`` y ``last_error``; tras ``MAX_ATTEMPTS`` deja de reintentarse en
cada operación pero sigue visible (``pending_report``). El manejador es
idempotente por ``event_id``/``payroll_run_id``: reentregar no duplica el
asiento.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("spj.hr.finance_wiring")

PAYROLL_PAID = "PAYROLL_PAID"
#: Eventos con efecto contable: sin consumidor NO se marcan despachados.
REQUIRES_CONSUMER = frozenset({PAYROLL_PAID})
MAX_ATTEMPTS = 10


def payroll_paid_to_finance(payload: dict) -> dict:
    """Los eventos encolados antes del 2026-10-10 no traían ``occurred_at``:
    se toma del instante de pago (``paid_at``)."""
    data = dict(payload)
    if not data.get("occurred_at") and data.get("paid_at"):
        data["occurred_at"] = data["paid_at"]
    return data


def wire_hr_finance(bus, connection) -> dict:
    from backend.application.event_handlers.finance.payroll_paid_handler import (
        PayrollPaidHandler,
    )

    handler = PayrollPaidHandler(connection)
    subscribe = getattr(bus, "subscribe", None)
    if subscribe is None:
        raise RuntimeError("El bus no expone subscribe()")

    def _to_finance(payload: dict) -> None:
        handler.handle(payroll_paid_to_finance(payload))

    try:
        subscribe(PAYROLL_PAID, _to_finance, priority=50, label="hr_finance_payroll_paid")
    except TypeError:
        subscribe(PAYROLL_PAID, _to_finance)
    return {"subscribed": [f"{PAYROLL_PAID}->finance"], "count": 1}


def _columns(connection) -> set[str]:
    return {str(r[1]) for r in connection.execute("PRAGMA table_info(hr_outbox)").fetchall()}


def dispatch_hr_outbox(connection, bus, *, limit: int = 200) -> dict:
    """Publica en orden los eventos PENDIENTES de ``hr_outbox`` (estricto)."""
    columns = _columns(connection)
    if not columns:
        return {"pending": 0, "dispatched": 0, "failed": 0, "without_consumer": 0}
    tracks_attempts = "attempts" in columns
    where = "status='PENDING'" + (f" AND attempts < {MAX_ATTEMPTS}" if tracks_attempts else "")
    pendientes = connection.execute(
        f"SELECT id, event_name, payload_json FROM hr_outbox WHERE {where}"
        " ORDER BY created_at LIMIT ?", (limit,)).fetchall()
    despachados = fallidos = sin_consumidor = 0
    for outbox_id, event_name, payload_json in pendientes:
        try:
            sobre = json.loads(payload_json)
            if not isinstance(sobre, dict):
                raise ValueError("el payload del outbox debe ser un objeto JSON")
            atendidos = bus.publish(event_name, sobre, strict=True)
            if event_name in REQUIRES_CONSUMER and not atendidos:
                sin_consumidor += 1
                _record_failure(connection, outbox_id, "sin consumidor registrado",
                                tracks_attempts)
                continue
            connection.execute(
                "UPDATE hr_outbox SET status='DISPATCHED', dispatched_at=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), outbox_id))
            connection.commit()
            despachados += 1
        except Exception as exc:
            fallidos += 1
            logger.exception("hr outbox: no se pudo despachar %s (%s)", outbox_id, event_name)
            try:
                connection.rollback()
            except Exception:
                pass
            _record_failure(connection, outbox_id, str(exc)[:500], tracks_attempts)
    return {"pending": len(pendientes), "dispatched": despachados, "failed": fallidos,
            "without_consumer": sin_consumidor}


def _record_failure(connection, outbox_id: str, error: str, tracks_attempts: bool) -> None:
    if not tracks_attempts:
        return
    connection.execute(
        "UPDATE hr_outbox SET attempts = attempts + 1, last_error=? WHERE id=?",
        (error, outbox_id))
    connection.commit()


def pending_report(connection) -> list[dict]:
    """Eventos que no llegaron: visibles con intentos y último error."""
    if "attempts" not in _columns(connection):
        return []
    rows = connection.execute(
        "SELECT id, event_name, attempts, last_error, created_at FROM hr_outbox"
        " WHERE status='PENDING' ORDER BY created_at").fetchall()
    return [dict(zip(("id", "event_name", "attempts", "last_error", "created_at"), r))
            for r in rows]

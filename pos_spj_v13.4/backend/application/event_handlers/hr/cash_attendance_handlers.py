"""Cash↔Attendance handlers — cash shift events become attendance punches.

Caja never calls RRHH directly; it publishes CASH_SHIFT_OPENED / CASH_SHIFT_CLOSED
and these handlers translate them into canonical attendance punches. The cash
shift id is the ``source_reference_id`` so repeated shift events are idempotent
and multiple cash shifts in a day do not create multiple workdays.

Auditoría RRHH cebf67a:

* HR-05 — Caja publica el sobre CANÓNICO (``entity_id``, ``timestamp`` y un
  ``payload`` anidado con ``cashier_user_id``); el manejador buscaba
  ``shift_id``/``opened_at`` planos, guardaba la hora de PROCESO, una referencia
  vacía y la clave constante ``cash-open-``. ``translate_cash_shift_event`` es el
  traductor contractual: el turno sale de ``entity_id``, la hora del evento
  original (nunca del reloj del consumidor) y la persona es el CAJERO del turno,
  no quien operó la apertura. Sin esos datos el evento se rechaza.
* HR-06 — consumir, resolver la identidad, registrar la marcación y marcar el
  evento procesado ocurren en UNA transacción y sólo si la marcación se
  registró. Un usuario sin empleado vinculado no pierde el evento: queda en
  ``hr_inbox`` y se aplica al vincularlo (``reprocess_pending_cash_attendance``).

Config flags (attendance.cash_open_marks_entry / cash_close_marks_exit) gate the
behavior; both default to true.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.application.use_cases.hr.attendance_use_cases import (
    RegisterAttendancePunchUseCase,
)
from backend.domain.hr.enums import AttendanceSource, PunchType
from backend.domain.hr.exceptions import HRDomainError
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.ids import derived_uuidv7

logger = logging.getLogger("spj.hr.cash_attendance")

CASH_SHIFT_OPENED = "CASH_SHIFT_OPENED"
CASH_SHIFT_CLOSED = "CASH_SHIFT_CLOSED"
#: Resultados del registro que dependen de datos de RR. HH. que se pueden
#: corregir (vincular, reactivar): el evento se retiene, no se pierde.
_RECOVERABLE_ERRORS = frozenset({"NOT_FOUND", "EMPLOYEE_INACTIVE"})


def _default_config(_key: str) -> bool:
    return True


@dataclass(frozen=True, slots=True)
class CashShiftAttendance:
    event_id: str
    event_name: str
    operation_id: str
    shift_id: str
    branch_id: str
    occurred_at: datetime
    cashier_user_id: str
    employee_id: str


def _parse_moment(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    moment = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def translate_cash_shift_event(payload: dict, event_name: str) -> CashShiftAttendance:
    """Sobre de Caja → datos de asistencia. Acepta el sobre canónico de Caja y
    el plano histórico de ``CloseCashShiftUseCase``; rechaza ausencias en vez
    de inventar hora, turno o clave."""
    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    time_key = "opened_at" if event_name == CASH_SHIFT_OPENED else "closed_at"

    def pick(*keys):
        for source in (inner, payload):
            for key in keys:
                value = source.get(key)
                if value not in (None, ""):
                    return value
        return None

    event_id = str(payload.get("event_id") or "").strip()
    operation_id = str(payload.get("operation_id") or "").strip()
    shift_id = str(pick("shift_id") or payload.get("entity_id") or "").strip()
    branch_id = str(pick("branch_id") or "").strip()
    raw_moment = pick(time_key) or payload.get("timestamp")
    cashier = str(pick("cashier_user_id") or payload.get("user_id") or "").strip()
    employee_id = str(pick("employee_id") or "").strip()
    missing = [name for name, value in (
        ("event_id", event_id), ("operation_id", operation_id), ("turno", shift_id),
        ("sucursal", branch_id), ("hora", raw_moment)) if not value]
    if not cashier and not employee_id:
        missing.append("cajero")
    if missing:
        raise HRDomainError(f"{event_name} incompleto: falta {', '.join(missing)}")
    try:
        occurred_at = _parse_moment(raw_moment)
    except ValueError as exc:
        raise HRDomainError(f"{event_name}: hora inválida {raw_moment!r}") from exc
    return CashShiftAttendance(event_id, event_name, operation_id, shift_id, branch_id,
                               occurred_at, cashier, employee_id)


class _CashAttendanceBase:
    event_name = ""
    punch_type: PunchType
    config_key = ""
    note = ""

    def __init__(self, connection, *, config_getter=None) -> None:
        self._connection = connection
        self._register = RegisterAttendancePunchUseCase()
        self._config = config_getter or _default_config

    def handle(self, payload: dict) -> None:
        if not self._config(self.config_key):
            return
        data = translate_cash_shift_event(payload, self.event_name)
        with HRUnitOfWork(self._connection) as uow:
            if uow.processed_events.was_processed(data.event_id):
                return
            employee_id = data.employee_id
            if not employee_id:
                employee = uow.employees.get_by_user_id(data.cashier_user_id)
                employee_id = employee.id if employee is not None else ""
            if not employee_id:
                self._hold(uow, payload, data,
                           f"El usuario {data.cashier_user_id} no está vinculado con un empleado")
                return
            registration = self._register.execute(
                self._connection, employee_id=employee_id, branch_id=data.branch_id,
                punch_type=self.punch_type, occurred_at=data.occurred_at,
                source=AttendanceSource.CASH_REGISTER,
                operation_id=derived_uuidv7(data.operation_id,
                                            f"hr-attendance-{self.punch_type.value}"),
                source_reference_id=data.shift_id,
                registered_by_user_id=data.cashier_user_id or None, notes=self.note)
            result = registration.result
            if not result.success:
                if result.error_code in _RECOVERABLE_ERRORS:
                    self._hold(uow, payload, data, result.message)
                    return
                raise HRDomainError(result.message)
            uow.processed_events.mark_processed(data.event_id, self.event_name,
                                                data.operation_id)
            uow.inbox.mark_processed(data.event_id)

    @staticmethod
    def _hold(uow, payload: dict, data: CashShiftAttendance, reason: str) -> None:
        logger.warning("asistencia por caja retenida (%s): %s", data.event_id, reason)
        uow.inbox.hold(event_id=data.event_id, event_name=data.event_name,
                       payload_json=json.dumps(payload, default=str),
                       user_id=data.cashier_user_id or None, error=reason)


class CashShiftOpenedAttendanceHandler(_CashAttendanceBase):
    """CASH_SHIFT_OPENED → registers ENTRY if configured and not already open."""

    event_name = CASH_SHIFT_OPENED
    punch_type = PunchType.ENTRY
    config_key = "attendance.cash_open_marks_entry"
    note = "Apertura de caja"


class CashShiftClosedAttendanceHandler(_CashAttendanceBase):
    """CASH_SHIFT_CLOSED → registers EXIT if configured."""

    event_name = CASH_SHIFT_CLOSED
    punch_type = PunchType.EXIT
    config_key = "attendance.cash_close_marks_exit"
    note = "Cierre de caja"


def reprocess_pending_cash_attendance(connection, *, user_id: str | None = None,
                                      config_getter=None) -> int:
    """Aplica los eventos de caja retenidos (p. ej. tras vincular al usuario
    con su empleado). Cada uno se aplica una sola vez; devuelve cuántos
    quedaron procesados."""
    handlers = {
        CASH_SHIFT_OPENED: CashShiftOpenedAttendanceHandler(
            connection, config_getter=config_getter),
        CASH_SHIFT_CLOSED: CashShiftClosedAttendanceHandler(
            connection, config_getter=config_getter),
    }
    with HRUnitOfWork(connection) as uow:
        pending = uow.inbox.list_pending(user_id=user_id)
    processed = 0
    for row in pending:
        handler = handlers.get(row["event_name"])
        if handler is None:
            continue
        try:
            handler.handle(json.loads(row["payload_json"]))
        except Exception:
            logger.exception("reproceso de asistencia por caja fallido (%s)", row["event_id"])
            continue
        with HRUnitOfWork(connection) as uow:
            if uow.processed_events.was_processed(row["event_id"]):
                processed += 1
    return processed


def wire_cash_attendance(bus, connection, *, config_getter=None) -> dict:
    """HR-03: Caja → asistencia en el arranque (antes ningún suscriptor)."""
    opened = CashShiftOpenedAttendanceHandler(connection, config_getter=config_getter)
    closed = CashShiftClosedAttendanceHandler(connection, config_getter=config_getter)
    subscribe = getattr(bus, "subscribe", None)
    if subscribe is None:
        raise RuntimeError("El bus no expone subscribe()")
    for event_name, handler in ((CASH_SHIFT_OPENED, opened), (CASH_SHIFT_CLOSED, closed)):
        try:
            subscribe(event_name, handler.handle, priority=80,
                      label=f"hr_attendance_{event_name.lower()}")
        except TypeError:
            subscribe(event_name, handler.handle)
    return {"subscribed": [f"{CASH_SHIFT_OPENED}->hr", f"{CASH_SHIFT_CLOSED}->hr"],
            "count": 2}

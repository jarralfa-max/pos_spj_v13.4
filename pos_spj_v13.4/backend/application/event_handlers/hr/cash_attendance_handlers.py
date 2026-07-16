"""Cash↔Attendance handlers — cash shift events become attendance punches.

Caja never calls RRHH directly; it publishes CASH_SHIFT_OPENED / CASH_SHIFT_CLOSED
and these handlers translate them into canonical attendance punches. The cash
shift id is the ``source_reference_id`` so repeated shift events are idempotent
and multiple cash shifts in a day do not create multiple workdays.

Config flags (attendance.cash_open_marks_entry / cash_close_marks_exit) gate the
behavior; both default to true.
"""

from __future__ import annotations

import logging
from datetime import datetime

from backend.application.use_cases.hr.attendance_use_cases import (
    RegisterAttendancePunchUseCase,
)
from backend.domain.hr.enums import AttendanceSource, PunchType
from backend.domain.hr.exceptions import HRDomainError, UserEmployeeLinkRequiredError
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork

logger = logging.getLogger("spj.hr.cash_attendance")


def _default_config(_key: str) -> bool:
    return True


class _CashAttendanceBase:
    """Shared idempotency + employee resolution for cash-driven punches."""

    def __init__(self, connection, *, config_getter=None) -> None:
        self._connection = connection
        self._register = RegisterAttendancePunchUseCase()
        self._config = config_getter or _default_config

    def _resolve_employee_id(self, payload: dict) -> str:
        employee_id = str(payload.get("employee_id") or "")
        if employee_id:
            return employee_id
        user_id = str(payload.get("user_id") or "")
        if not user_id:
            raise UserEmployeeLinkRequiredError(
                "El evento de caja no incluye employee_id ni user_id"
            )
        with HRUnitOfWork(self._connection) as uow:
            employee = uow.employees.get_by_user_id(user_id)
        if employee is None:
            raise UserEmployeeLinkRequiredError(
                f"El usuario {user_id} no está vinculado con un empleado; "
                "no se puede registrar asistencia"
            )
        return employee.id

    @staticmethod
    def _mark_processed(uow: HRUnitOfWork, event_id: str, event_name: str,
                        operation_id: str) -> bool:
        if uow.processed_events.was_processed(event_id):
            return True
        uow.processed_events.mark_processed(event_id, event_name, operation_id)
        return False


class CashShiftOpenedAttendanceHandler(_CashAttendanceBase):
    """CASH_SHIFT_OPENED → registers ENTRY if configured and not already open."""

    def handle(self, payload: dict) -> None:
        if not self._config("attendance.cash_open_marks_entry"):
            return
        event_id = str(payload.get("event_id") or "")
        operation_id = str(payload.get("operation_id") or "")
        if not event_id or not operation_id:
            raise HRDomainError("CASH_SHIFT_OPENED requiere event_id y operation_id")

        with HRUnitOfWork(self._connection) as uow:
            if self._mark_processed(uow, event_id, "CASH_SHIFT_OPENED", operation_id):
                return

        employee_id = self._resolve_employee_id(payload)
        branch_id = str(payload.get("branch_id") or "")
        shift_id = str(payload.get("shift_id") or "")
        occurred_at = _parse_dt(payload.get("opened_at"))
        # source_reference_id = shift_id → repeated open events are idempotent and
        # multiple shifts in a day still reuse the same workday (one per date).
        self._register.execute(
            self._connection, employee_id=employee_id, branch_id=branch_id,
            punch_type=PunchType.ENTRY, occurred_at=occurred_at,
            source=AttendanceSource.CASH_REGISTER, operation_id=f"cash-open-{shift_id}",
            source_reference_id=shift_id,
            registered_by_user_id=payload.get("user_id"),
            notes="Apertura de caja")


class CashShiftClosedAttendanceHandler(_CashAttendanceBase):
    """CASH_SHIFT_CLOSED → registers EXIT if configured and an entry is open."""

    def handle(self, payload: dict) -> None:
        if not self._config("attendance.cash_close_marks_exit"):
            return
        event_id = str(payload.get("event_id") or "")
        operation_id = str(payload.get("operation_id") or "")
        if not event_id or not operation_id:
            raise HRDomainError("CASH_SHIFT_CLOSED requiere event_id y operation_id")

        with HRUnitOfWork(self._connection) as uow:
            if self._mark_processed(uow, event_id, "CASH_SHIFT_CLOSED", operation_id):
                return

        employee_id = self._resolve_employee_id(payload)
        branch_id = str(payload.get("branch_id") or "")
        shift_id = str(payload.get("shift_id") or "")
        occurred_at = _parse_dt(payload.get("closed_at"))
        self._register.execute(
            self._connection, employee_id=employee_id, branch_id=branch_id,
            punch_type=PunchType.EXIT, occurred_at=occurred_at,
            source=AttendanceSource.CASH_REGISTER, operation_id=f"cash-close-{shift_id}",
            source_reference_id=shift_id,
            registered_by_user_id=payload.get("user_id"),
            notes="Cierre de caja")


def _parse_dt(value) -> datetime:
    from datetime import timezone
    if isinstance(value, datetime):
        return value
    if value:
        return datetime.fromisoformat(str(value))
    return datetime.now(timezone.utc)

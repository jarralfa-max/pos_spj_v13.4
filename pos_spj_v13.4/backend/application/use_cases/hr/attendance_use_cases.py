"""Attendance use cases — punch registration, manual entry, adjustments, workday.

Central idempotency and sequencing rules live here so the cash handler and the
manual UI share one canonical path:
- a repeated ``operation_id`` returns the existing punch;
- a repeated cash ``(source, source_reference_id, punch_type)`` returns idempotently;
- an ENTRY on a workday with an open entry does not duplicate;
- an EXIT without an open entry creates a MISSING_ENTRY incident (never invents time).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from backend.application.use_cases.hr.hr_result import HRResult
from backend.domain.hr.entities import (
    AttendanceAdjustment,
    AttendancePunch,
    AttendanceWorkday,
)
from backend.domain.hr.enums import (
    AttendanceIncidentType,
    AttendanceSource,
    PunchType,
    WorkdayStatus,
)
from backend.domain.hr.exceptions import HRDomainError
from backend.domain.hr.policies.attendance_policy import AttendancePolicy
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy
from backend.domain.hr.services.workday_builder import WorkdayBuilder
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


@dataclass(frozen=True, slots=True)
class PunchRegistration:
    result: HRResult
    duplicated: bool = False
    incident_created: bool = False


class RegisterAttendancePunchUseCase:
    """Canonical punch registration used by every source (cash, manual, clock)."""

    def __init__(self) -> None:
        self._policy = AttendancePolicy()
        self._builder = WorkdayBuilder()

    def execute(
        self,
        connection,
        *,
        employee_id: str,
        branch_id: str,
        punch_type: PunchType,
        occurred_at: datetime,
        source: AttendanceSource,
        operation_id: str,
        source_reference_id: str | None = None,
        registered_by_user_id: str | None = None,
        device_id: str | None = None,
        notes: str | None = None,
    ) -> PunchRegistration:
        with HRUnitOfWork(connection) as uow:
            employee = uow.employees.get(employee_id)
            if employee is None:
                return PunchRegistration(HRResult.fail(
                    "El empleado no existe", "NOT_FOUND", operation_id=operation_id))
            if not employee.active:
                return PunchRegistration(HRResult.fail(
                    "El empleado está inactivo", "EMPLOYEE_INACTIVE",
                    operation_id=operation_id))

            # Idempotency by operation_id.
            existing = uow.attendance.find_punch_by_operation_id(operation_id)
            if existing is not None:
                return PunchRegistration(HRResult.ok(
                    "Marcación ya registrada", entity_id=existing.id,
                    operation_id=operation_id), duplicated=True)
            # Idempotency by cash source reference.
            if source_reference_id is not None:
                dup = uow.attendance.find_punch_by_source_reference(
                    source.value, source_reference_id, punch_type.value)
                if dup is not None:
                    return PunchRegistration(HRResult.ok(
                        "Ya existía una marcación para esta referencia; no se duplicó",
                        entity_id=dup.id, operation_id=operation_id), duplicated=True)

            work_date = occurred_at.date()
            workday = uow.attendance.find_workday(employee_id, work_date)
            if workday is None:
                workday = AttendanceWorkday.create(employee_id, branch_id, work_date)
                uow.attendance.save_workday(workday)

            incident = False
            if punch_type is PunchType.ENTRY:
                if workday.has_open_entry():
                    return PunchRegistration(HRResult.ok(
                        "Ya existía una entrada laboral registrada; no se creó un duplicado",
                        entity_id=workday.id, operation_id=operation_id), duplicated=True)
            else:  # EXIT
                if workday.first_entry_at is None:
                    incident = True

            punch = AttendancePunch.create(
                employee_id, branch_id, punch_type, occurred_at, source, operation_id,
                source_reference_id=source_reference_id,
                registered_by_user_id=registered_by_user_id, device_id=device_id,
                notes=notes)
            uow.attendance.save_punch(punch, workday_id=workday.id)

            shift = self._resolve_shift(uow, employee_id, work_date)
            punches = uow.attendance.list_punches_for_workday(workday.id)
            self._builder.rebuild(workday, punches, shift)
            if incident and workday.status is WorkdayStatus.INCIDENT:
                workday.incident_type = AttendanceIncidentType.MISSING_ENTRY
            uow.attendance.update_workday(workday)

            event_name = (EventName.ATTENDANCE_ENTRY_REGISTERED
                          if punch_type is PunchType.ENTRY
                          else EventName.ATTENDANCE_EXIT_REGISTERED)
            uow.outbox.enqueue(new_uuid(), event_name.value, json.dumps({
                "punch_id": punch.id, "employee_id": employee_id,
                "workday_id": workday.id, "operation_id": operation_id,
                "occurred_at": occurred_at.isoformat()}), operation_id)
            uow.outbox.enqueue(new_uuid(), EventName.ATTENDANCE_PUNCH_REGISTERED.value,
                               json.dumps({"punch_id": punch.id,
                                           "punch_type": punch_type.value}), operation_id)

            if incident:
                uow.outbox.enqueue(new_uuid(),
                                   EventName.ATTENDANCE_INCIDENT_CREATED.value,
                                   json.dumps({"workday_id": workday.id,
                                               "incident": "MISSING_ENTRY"}), operation_id)
                uow.audit.record(action="ATTENDANCE_INCIDENT", actor_user_id=registered_by_user_id,
                                 entity_type="workday", entity_id=workday.id,
                                 detail="MISSING_ENTRY", operation_id=operation_id)
                message = ("No se encontró una entrada laboral. Se creó una incidencia "
                           "para revisión de RRHH.")
            elif punch_type is PunchType.ENTRY:
                message = f"Tu entrada se registró a las {occurred_at.strftime('%H:%M')}."
            else:
                message = f"Tu salida se registró a las {occurred_at.strftime('%H:%M')}."

            return PunchRegistration(
                HRResult.ok(message, entity_id=punch.id, operation_id=operation_id,
                            workday_id=workday.id),
                incident_created=incident)

    @staticmethod
    def _resolve_shift(uow: HRUnitOfWork, employee_id: str, work_date):
        assignment = uow.shifts.find_assignment_for(employee_id, work_date)
        if assignment is None:
            return None
        return uow.shifts.get(assignment.work_shift_id)


class RegisterManualAttendanceUseCase:
    """Manual entry/exit for employees who don't open/close a cash register."""

    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._register = RegisterAttendancePunchUseCase()

    def execute(self, connection, *, actor_user_id: str, employee_id: str, branch_id: str,
                punch_type: str, occurred_at: datetime, reason: str, operation_id: str,
                notes: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, "hr.attendance.register_manual")
        if not reason or not reason.strip():
            return HRResult.fail("El registro manual requiere un motivo", "VALIDATION",
                                 operation_id=operation_id)
        registration = self._register.execute(
            connection, employee_id=employee_id, branch_id=branch_id,
            punch_type=PunchType(punch_type), occurred_at=occurred_at,
            source=AttendanceSource.MANUAL, operation_id=operation_id,
            registered_by_user_id=actor_user_id,
            notes=f"{reason.strip()}" + (f" | {notes}" if notes else ""))
        with HRUnitOfWork(connection) as uow:
            uow.audit.record(action="ATTENDANCE_MANUAL", actor_user_id=actor_user_id,
                             entity_type="workday",
                             entity_id=registration.result.data.get("workday_id"),
                             detail=f"{punch_type}: {reason.strip()}",
                             operation_id=operation_id)
        return registration.result


class RequestAttendanceAdjustmentUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, workday_id: str, field_name: str,
                requested_value: str, reason: str, operation_id: str,
                original_punch_id: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, "hr.attendance.adjust")
        with HRUnitOfWork(connection) as uow:
            if uow.adjustments.find_by_operation_id(operation_id):
                return HRResult.ok("Ajuste ya solicitado", operation_id=operation_id)
            workday = uow.attendance.get_workday(workday_id)
            if workday is None:
                return HRResult.fail("La jornada no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            previous = getattr(workday, field_name, None)
            try:
                adjustment = AttendanceAdjustment.create(
                    workday.employee_id, workday_id, field_name,
                    str(previous) if previous is not None else None, requested_value,
                    reason, actor_user_id, operation_id,
                    original_punch_id=original_punch_id)
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.adjustments.save(adjustment)
            uow.audit.record(action="ATTENDANCE_ADJUSTMENT_REQUESTED",
                             actor_user_id=actor_user_id, entity_type="adjustment",
                             entity_id=adjustment.id, detail=reason,
                             operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(),
                               EventName.ATTENDANCE_ADJUSTMENT_REQUESTED.value,
                               json.dumps({"adjustment_id": adjustment.id}), operation_id)
        return HRResult.ok("Ajuste solicitado", entity_id=adjustment.id,
                           operation_id=operation_id)


class ApproveAttendanceAdjustmentUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._builder = WorkdayBuilder()

    def execute(self, connection, *, actor_user_id: str, adjustment_id: str,
                operation_id: str, approve: bool = True) -> HRResult:
        self._auth.require(actor_user_id, "hr.attendance.approve_adjustment")
        with HRUnitOfWork(connection) as uow:
            adjustment = uow.adjustments.get(adjustment_id)
            if adjustment is None:
                return HRResult.fail("El ajuste no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            try:
                if approve:
                    adjustment.approve(actor_user_id)
                else:
                    adjustment.reject(actor_user_id)
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.adjustments.update(adjustment)

            if approve:
                workday = uow.attendance.get_workday(adjustment.workday_id)
                if workday is not None:
                    new_value = datetime.fromisoformat(adjustment.requested_value)
                    setattr(workday, adjustment.field_name, new_value)
                    workday.status = WorkdayStatus.ADJUSTED
                    workday.updated_at = adjustment.approved_at
                    uow.attendance.update_workday(workday)
                uow.outbox.enqueue(new_uuid(),
                                   EventName.ATTENDANCE_ADJUSTMENT_APPROVED.value,
                                   json.dumps({"adjustment_id": adjustment.id}),
                                   operation_id)
            uow.audit.record(
                action="ATTENDANCE_ADJUSTMENT_" + ("APPROVED" if approve else "REJECTED"),
                actor_user_id=actor_user_id, entity_type="adjustment",
                entity_id=adjustment.id, detail="", operation_id=operation_id)
        return HRResult.ok("Ajuste procesado", entity_id=adjustment_id,
                           operation_id=operation_id)


class RecalculateWorkdayUseCase:
    def __init__(self) -> None:
        self._builder = WorkdayBuilder()

    def execute(self, connection, *, workday_id: str) -> HRResult:
        with HRUnitOfWork(connection) as uow:
            workday = uow.attendance.get_workday(workday_id)
            if workday is None:
                return HRResult.fail("La jornada no existe", "NOT_FOUND")
            punches = uow.attendance.list_punches_for_workday(workday_id)
            shift = None
            if workday.scheduled_shift_id:
                shift = uow.shifts.get(workday.scheduled_shift_id)
            self._builder.rebuild(workday, punches, shift)
            uow.attendance.update_workday(workday)
        return HRResult.ok("Jornada recalculada", entity_id=workday_id)

"""Attendance use cases — punch registration, manual entry, adjustments, workday.

Central idempotency and sequencing rules live here so the cash handler and the
manual UI share one canonical path:
- a repeated ``operation_id`` returns the existing punch;
- a repeated cash ``(source, source_reference_id, punch_type)`` returns idempotently;
- an ENTRY on a workday with an open entry does not duplicate;
- an EXIT without an open entry creates an incident (never invents time and
  never extends a closed workday).

Auditoría RRHH cebf67a:
- HR-22: el instante se guarda en UTC y la FECHA LABORAL se resuelve en la zona
  de la sucursal; una hora capturada sin zona es hora local de la sucursal.
- HR-13: una salida pertenece a la jornada con entrada abierta (turno nocturno
  22:00→06:00 es UNA jornada de ocho horas), dentro de una ventana máxima.
- HR-16: la jornada guarda el turno resuelto; registrar y recalcular usan el
  mismo resolvedor y dan el mismo resultado.
- HR-17: los ajustes aprobados se reaplican en cada recálculo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

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
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy, HRPermission
from backend.domain.hr.services.workday_builder import ADJUSTABLE_FIELDS, WorkdayBuilder
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.business_dates import as_aware, resolve_timezone
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


@dataclass(frozen=True, slots=True)
class PunchRegistration:
    result: HRResult
    duplicated: bool = False
    incident_created: bool = False


def _branch_zone(uow: HRUnitOfWork, branch_id: str | None):
    name = uow.calendar.timezone_name(branch_id)
    return name, resolve_timezone(name)


def resolve_workday_shift(uow: HRUnitOfWork, workday: AttendanceWorkday):
    """Resolvedor ÚNICO del turno de una jornada (registro y recálculo)."""
    if workday.scheduled_shift_id:
        shift = uow.shifts.get(workday.scheduled_shift_id)
        if shift is not None:
            return shift
    assignment = uow.shifts.find_assignment_for(workday.employee_id, workday.work_date)
    if assignment is None:
        return None
    return uow.shifts.get(assignment.work_shift_id)


def rebuild_workday(uow: HRUnitOfWork, builder: WorkdayBuilder,
                    workday: AttendanceWorkday) -> AttendanceWorkday:
    """Recalcula la jornada con sus marcaciones + ajustes aprobados + turno
    resuelto + zona de la sucursal, y deja guardado el turno usado."""
    shift = resolve_workday_shift(uow, workday)
    workday.scheduled_shift_id = shift.id if shift is not None else None
    _, zone = _branch_zone(uow, workday.branch_id)
    builder.rebuild(workday, uow.attendance.list_punches_for_workday(workday.id), shift,
                    adjustments=uow.adjustments.list_approved_for_workday(workday.id),
                    tz=zone)
    workday.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    uow.attendance.update_workday(workday)
    return workday


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

            zone_name, zone = _branch_zone(uow, branch_id)
            moment = as_aware(occurred_at, zone).astimezone(timezone.utc)
            local_day = moment.astimezone(zone).date()

            workday = None
            if punch_type is PunchType.EXIT:
                candidate = uow.attendance.find_open_workday(
                    employee_id, since=local_day - timedelta(days=1))
                window = timedelta(hours=self._policy.MAX_OPEN_WORKDAY_HOURS)
                opened = candidate.first_entry_at if candidate is not None else None
                if opened is not None and opened.tzinfo is None:
                    opened = opened.replace(tzinfo=timezone.utc)   # filas previas sin zona
                if opened is not None and timedelta(0) <= moment - opened <= window:
                    workday = candidate
            if workday is None:
                workday = uow.attendance.find_workday(employee_id, local_day)
            if workday is None:
                workday = AttendanceWorkday.create(employee_id, branch_id, local_day)
                uow.attendance.save_workday(workday)

            if punch_type is PunchType.ENTRY and workday.has_open_entry():
                return PunchRegistration(HRResult.ok(
                    "Ya existía una entrada laboral registrada; no se creó un duplicado",
                    entity_id=workday.id, operation_id=operation_id), duplicated=True)

            punch = AttendancePunch.create(
                employee_id, branch_id, punch_type, moment, source, operation_id,
                timezone_name=zone_name, source_reference_id=source_reference_id,
                registered_by_user_id=registered_by_user_id, device_id=device_id,
                notes=notes)
            uow.attendance.save_punch(punch, workday_id=workday.id)
            rebuild_workday(uow, self._builder, workday)
            incident = (punch_type is PunchType.EXIT
                        and workday.status is WorkdayStatus.INCIDENT)

            event_name = (EventName.ATTENDANCE_ENTRY_REGISTERED
                          if punch_type is PunchType.ENTRY
                          else EventName.ATTENDANCE_EXIT_REGISTERED)
            uow.outbox.enqueue(new_uuid(), event_name.value, json.dumps({
                "punch_id": punch.id, "employee_id": employee_id,
                "workday_id": workday.id, "operation_id": operation_id,
                "occurred_at": moment.isoformat()}), operation_id)
            uow.outbox.enqueue(new_uuid(), EventName.ATTENDANCE_PUNCH_REGISTERED.value,
                               json.dumps({"punch_id": punch.id,
                                           "punch_type": punch_type.value}), operation_id)

            local_clock = moment.astimezone(zone).strftime("%H:%M")
            if incident:
                kind = (workday.incident_type.value if workday.incident_type
                        else AttendanceIncidentType.MISSING_ENTRY.value)
                uow.outbox.enqueue(new_uuid(),
                                   EventName.ATTENDANCE_INCIDENT_CREATED.value,
                                   json.dumps({"workday_id": workday.id,
                                               "incident": kind}), operation_id)
                uow.audit.record(action="ATTENDANCE_INCIDENT", actor_user_id=registered_by_user_id,
                                 entity_type="workday", entity_id=workday.id,
                                 detail=kind, operation_id=operation_id)
                if kind == AttendanceIncidentType.OUT_OF_SEQUENCE.value:
                    message = ("La jornada no tenía una entrada abierta: la salida se "
                               "registró como incidencia para revisión y no sumó horas.")
                else:
                    message = ("No se encontró una entrada laboral. Se creó una incidencia "
                               "para revisión de RRHH.")
            elif punch_type is PunchType.ENTRY:
                message = f"Tu entrada se registró a las {local_clock}."
            else:
                message = f"Tu salida se registró a las {local_clock}."

            return PunchRegistration(
                HRResult.ok(message, entity_id=punch.id, operation_id=operation_id,
                            workday_id=workday.id),
                incident_created=incident)


class RegisterManualAttendanceUseCase:
    """Manual entry/exit for employees who don't open/close a cash register."""

    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._register = RegisterAttendancePunchUseCase()

    def execute(self, connection, *, actor_user_id: str, employee_id: str, branch_id: str,
                punch_type: str, occurred_at: datetime, reason: str, operation_id: str,
                notes: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.ATTENDANCE_MANUAL)
        self._auth.require_branch(actor_user_id, branch_id)
        if not reason or not reason.strip():
            return HRResult.fail("El registro manual requiere un motivo", "VALIDATION",
                                 operation_id=operation_id)
        with HRUnitOfWork(connection) as uow:
            employee = uow.employees.get(employee_id)
            if employee is None:
                return HRResult.fail("El empleado no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            self._auth.require_branch(actor_user_id, employee.branch_id)
            registration = self._register.execute(
                connection, employee_id=employee_id, branch_id=branch_id,
                punch_type=PunchType(punch_type), occurred_at=occurred_at,
                source=AttendanceSource.MANUAL, operation_id=operation_id,
                registered_by_user_id=actor_user_id,
                notes=f"{reason.strip()}" + (f" | {notes}" if notes else ""))
            if registration.result.success and not registration.duplicated:
                uow.audit.record(action="ATTENDANCE_MANUAL", actor_user_id=actor_user_id,
                                 entity_type="workday",
                                 entity_id=registration.result.data.get("workday_id"),
                                 detail=f"{punch_type}: {reason.strip()}",
                                 operation_id=operation_id)
        return registration.result


def _parse_requested_moment(raw, zone) -> datetime:
    if isinstance(raw, datetime):
        moment = raw
    else:
        try:
            moment = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise HRDomainError(f"Fecha y hora inválida: {raw!r}") from exc
    return as_aware(moment, zone).astimezone(timezone.utc)


class RequestAttendanceAdjustmentUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._builder = WorkdayBuilder()

    def execute(self, connection, *, actor_user_id: str, workday_id: str, field_name: str,
                requested_value, reason: str, operation_id: str,
                original_punch_id: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.ATTENDANCE_ADJUST)
        with HRUnitOfWork(connection) as uow:
            if uow.adjustments.find_by_operation_id(operation_id):
                return HRResult.ok("Ajuste ya solicitado", operation_id=operation_id)
            workday = uow.attendance.get_workday(workday_id)
            if workday is None:
                return HRResult.fail("La jornada no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            self._auth.require_branch(actor_user_id, workday.branch_id)
            try:
                if field_name not in ADJUSTABLE_FIELDS:
                    raise HRDomainError(
                        "Sólo se ajusta la hora de entrada o la de salida de la jornada")
                _, zone = _branch_zone(uow, workday.branch_id)
                moment = _parse_requested_moment(requested_value, zone)
                local_day = moment.astimezone(zone).date()
                if not (workday.work_date <= local_day <= workday.work_date + timedelta(days=1)):
                    raise HRDomainError(
                        "La hora solicitada no corresponde a la fecha de la jornada")
                previous = getattr(workday, field_name, None)
                adjustment = AttendanceAdjustment.create(
                    workday.employee_id, workday_id, field_name,
                    previous.isoformat() if previous is not None else None,
                    moment.isoformat(), reason, actor_user_id, operation_id,
                    original_punch_id=original_punch_id)
                self._enforce_sequence(uow, workday, adjustment)
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

    def _enforce_sequence(self, uow, workday: AttendanceWorkday,
                          adjustment: AttendanceAdjustment) -> None:
        """Simula la jornada con el ajuste: la entrada debe quedar antes de la
        salida (no se aprueban horas incoherentes)."""
        from copy import copy
        from backend.domain.hr.enums import AdjustmentStatus

        preview = copy(adjustment)
        preview.status = AdjustmentStatus.APPROVED
        simulated = copy(workday)
        approved = uow.adjustments.list_approved_for_workday(workday.id)
        self._builder.rebuild(simulated, uow.attendance.list_punches_for_workday(workday.id),
                              None, adjustments=[*approved, preview])
        if simulated.status is WorkdayStatus.INCIDENT or (
                simulated.first_entry_at is not None and simulated.last_exit_at is not None
                and simulated.last_exit_at <= simulated.first_entry_at):
            raise HRDomainError(
                "Con este ajuste la jornada quedaría fuera de secuencia "
                "(la salida antes de la entrada)")


class ApproveAttendanceAdjustmentUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._builder = WorkdayBuilder()

    def execute(self, connection, *, actor_user_id: str, adjustment_id: str,
                operation_id: str, approve: bool = True) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.ATTENDANCE_APPROVE_ADJUSTMENT)
        with HRUnitOfWork(connection) as uow:
            adjustment = uow.adjustments.get(adjustment_id)
            if adjustment is None:
                return HRResult.fail("El ajuste no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            workday = uow.attendance.get_workday(adjustment.workday_id)
            if workday is not None:
                self._auth.require_branch(actor_user_id, workday.branch_id)
            try:
                if approve:
                    adjustment.approve(actor_user_id)
                else:
                    adjustment.reject(actor_user_id)
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.adjustments.update(adjustment)

            if approve:
                # HR-17: la corrección cambia los totales EN LA MISMA transacción
                # y sobrevive a cualquier recálculo posterior.
                if workday is not None:
                    rebuild_workday(uow, self._builder, workday)
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
            rebuild_workday(uow, self._builder, workday)
        return HRResult.ok("Jornada recalculada", entity_id=workday_id)

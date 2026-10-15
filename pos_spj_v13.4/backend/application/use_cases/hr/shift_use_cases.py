"""Work shift use cases — create shifts and assign them to employees.

Auditoría RRHH cebf67a HR-16: una asignación que se solapa (mismas fechas y
algún día de la semana en común) con otra del empleado se rechaza — antes el
resolvedor tomaba "la más reciente" y el turno efectivo era ambiguo. El turno
debe ser de la sucursal del empleado o general.
"""

from __future__ import annotations

import json
from datetime import date, time

from backend.application.use_cases.hr.hr_result import HRResult
from backend.domain.hr.entities import ShiftAssignment, WorkShift
from backend.domain.hr.exceptions import HRDomainError
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy, HRPermission
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


def _ranges_overlap(a_from: date, a_to: date | None, b_from: date, b_to: date | None) -> bool:
    far = date.max
    return a_from <= (b_to or far) and b_from <= (a_to or far)


class CreateShiftUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, name: str, start_time: time,
                end_time: time, break_minutes: int = 0, late_tolerance_minutes: int = 0,
                branch_id: str | None = None, operation_id: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.SHIFT_MANAGE)
        if branch_id:
            self._auth.require_branch(actor_user_id, branch_id)
        try:
            shift = WorkShift.create(name, start_time, end_time,
                                     break_minutes=break_minutes,
                                     late_tolerance_minutes=late_tolerance_minutes,
                                     branch_id=branch_id)
            if break_minutes >= shift.span_minutes():
                raise HRDomainError("El descanso no puede durar lo mismo o más que el turno")
        except HRDomainError as exc:
            return HRResult.fail(str(exc), "VALIDATION")
        with HRUnitOfWork(connection) as uow:
            uow.shifts.save(shift)
            uow.audit.record(action="WORK_SHIFT_CREATED", actor_user_id=actor_user_id,
                             entity_type="work_shift", entity_id=shift.id, detail=name,
                             operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(), EventName.WORK_SHIFT_CREATED.value,
                               json.dumps({"shift_id": shift.id, "name": name}),
                               operation_id or new_uuid())
        return HRResult.ok("Turno creado", entity_id=shift.id)


class AssignShiftUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, employee_id: str,
                work_shift_id: str, effective_from: date, weekdays: tuple[int, ...],
                branch_id: str | None = None, effective_to: date | None = None,
                operation_id: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, HRPermission.SHIFT_MANAGE)
        with HRUnitOfWork(connection) as uow:
            employee = uow.employees.get(employee_id)
            if employee is None:
                return HRResult.fail("El empleado no existe", "NOT_FOUND")
            self._auth.require_branch(actor_user_id, employee.branch_id)
            shift = uow.shifts.get(work_shift_id)
            if shift is None or not shift.active:
                return HRResult.fail("El turno no existe", "NOT_FOUND")
            if shift.branch_id and shift.branch_id != employee.branch_id:
                return HRResult.fail("El turno pertenece a otra sucursal", "BRANCH_MISMATCH")
            try:
                assignment = ShiftAssignment.create(
                    employee_id, work_shift_id, effective_from, weekdays,
                    branch_id=branch_id or employee.branch_id, effective_to=effective_to)
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "VALIDATION")
            for other in uow.shifts.list_assignments(employee_id):
                if (_ranges_overlap(other.effective_from, other.effective_to,
                                    assignment.effective_from, assignment.effective_to)
                        and set(other.weekdays) & set(assignment.weekdays)):
                    return HRResult.fail(
                        f"Se solapa con otra asignación vigente desde {other.effective_from}"
                        " en los mismos días; ciérrela antes de asignar otro turno",
                        "SHIFT_OVERLAP")
            uow.shifts.save_assignment(assignment)
            uow.audit.record(action="WORK_SHIFT_ASSIGNED", actor_user_id=actor_user_id,
                             entity_type="employee", entity_id=employee_id,
                             detail=f"{shift.name} desde {effective_from}",
                             operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(), EventName.WORK_SHIFT_ASSIGNED.value,
                               json.dumps({"assignment_id": assignment.id,
                                           "employee_id": employee_id}),
                               operation_id or new_uuid())
        return HRResult.ok("Turno asignado", entity_id=assignment.id)

"""Work shift use cases — create shifts and assign them to employees."""

from __future__ import annotations

import json
from datetime import date, time

from backend.application.use_cases.hr.hr_result import HRResult
from backend.domain.hr.entities import ShiftAssignment, WorkShift
from backend.domain.hr.exceptions import HRDomainError
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class CreateShiftUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, name: str, start_time: time,
                end_time: time, break_minutes: int = 0, late_tolerance_minutes: int = 0,
                branch_id: str | None = None, operation_id: str | None = None) -> HRResult:
        self._auth.require(actor_user_id, "hr.shift.manage")
        try:
            shift = WorkShift.create(name, start_time, end_time,
                                     break_minutes=break_minutes,
                                     late_tolerance_minutes=late_tolerance_minutes,
                                     branch_id=branch_id)
        except HRDomainError as exc:
            return HRResult.fail(str(exc), "VALIDATION")
        with HRUnitOfWork(connection) as uow:
            uow.shifts.save(shift)
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
        self._auth.require(actor_user_id, "hr.shift.manage")
        with HRUnitOfWork(connection) as uow:
            if uow.employees.get(employee_id) is None:
                return HRResult.fail("El empleado no existe", "NOT_FOUND")
            if uow.shifts.get(work_shift_id) is None:
                return HRResult.fail("El turno no existe", "NOT_FOUND")
            try:
                assignment = ShiftAssignment.create(
                    employee_id, work_shift_id, effective_from, weekdays,
                    branch_id=branch_id, effective_to=effective_to)
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "VALIDATION")
            uow.shifts.save_assignment(assignment)
            uow.outbox.enqueue(new_uuid(), EventName.WORK_SHIFT_ASSIGNED.value,
                               json.dumps({"assignment_id": assignment.id,
                                           "employee_id": employee_id}),
                               operation_id or new_uuid())
        return HRResult.ok("Turno asignado", entity_id=assignment.id)

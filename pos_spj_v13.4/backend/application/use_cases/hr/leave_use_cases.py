"""Leave use cases — request, approve, reject, cancel with validations."""

from __future__ import annotations

import json
from datetime import date

from backend.application.use_cases.hr.hr_result import HRResult
from backend.domain.hr.entities import LeaveRequest
from backend.domain.hr.enums import LeaveStatus, LeaveType
from backend.domain.hr.exceptions import HRDomainError
from backend.domain.hr.policies.authorization_policy import AuthorizationPolicy
from backend.domain.hr.policies.leave_policy import LeavePolicy
from backend.infrastructure.db.repositories.hr.unit_of_work import HRUnitOfWork
from backend.shared.events.event_names import EventName
from backend.shared.ids import new_uuid


class RequestLeaveUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None,
                 *, annual_vacation_days: int = 12) -> None:
        self._auth = authorization or AuthorizationPolicy()
        self._policy = LeavePolicy()
        self._annual_days = annual_vacation_days

    def execute(self, connection, *, actor_user_id: str, employee_id: str, branch_id: str,
                leave_type: str, start_date: date, end_date: date, reason: str,
                operation_id: str) -> HRResult:
        self._auth.require(actor_user_id, "hr.leave.request")
        with HRUnitOfWork(connection) as uow:
            if uow.leaves.find_by_operation_id(operation_id):
                return HRResult.ok("Solicitud ya registrada", operation_id=operation_id)
            employee = uow.employees.get(employee_id)
            if employee is None:
                return HRResult.fail("El empleado no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            if not employee.active:
                return HRResult.fail("El empleado está inactivo", "EMPLOYEE_INACTIVE",
                                     operation_id=operation_id)
            existing = uow.leaves.list_by_employee(employee_id)
            try:
                self._policy.enforce_dates(start_date, end_date)
                self._policy.enforce_no_overlap(start_date, end_date, existing)
                leave_type_enum = LeaveType(leave_type)
                request = LeaveRequest.create(
                    employee_id, branch_id, leave_type_enum, start_date, end_date,
                    reason, actor_user_id, operation_id)
                used = sum(r.requested_days for r in existing
                           if r.leave_type is LeaveType.VACATION
                           and r.status in (LeaveStatus.APPROVED, LeaveStatus.PENDING))
                self._policy.enforce_balance(leave_type_enum, request.requested_days,
                                             self._annual_days - used)
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.leaves.save(request)
            uow.audit.record(action="LEAVE_REQUESTED", actor_user_id=actor_user_id,
                             entity_type="leave", entity_id=request.id, detail=leave_type,
                             operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(), EventName.LEAVE_REQUESTED.value,
                               json.dumps({"leave_id": request.id,
                                           "employee_id": employee_id}), operation_id)
        return HRResult.ok("Solicitud registrada", entity_id=request.id,
                           operation_id=operation_id)


class ApproveLeaveUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, leave_id: str,
                operation_id: str, approve: bool = True) -> HRResult:
        self._auth.require(actor_user_id, "hr.leave.approve")
        with HRUnitOfWork(connection) as uow:
            request = uow.leaves.get(leave_id)
            if request is None:
                return HRResult.fail("La solicitud no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            try:
                if approve:
                    request.approve(actor_user_id)
                    event = EventName.LEAVE_APPROVED
                else:
                    request.reject(actor_user_id)
                    event = EventName.LEAVE_REJECTED
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.leaves.update(request)
            uow.audit.record(action=event.value, actor_user_id=actor_user_id,
                             entity_type="leave", entity_id=leave_id, detail="",
                             operation_id=operation_id)
            uow.outbox.enqueue(new_uuid(), event.value,
                               json.dumps({"leave_id": leave_id}), operation_id)
        return HRResult.ok("Solicitud procesada", entity_id=leave_id,
                           operation_id=operation_id)


class CancelLeaveUseCase:
    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._auth = authorization or AuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, leave_id: str,
                operation_id: str) -> HRResult:
        self._auth.require(actor_user_id, "hr.leave.request")
        with HRUnitOfWork(connection) as uow:
            request = uow.leaves.get(leave_id)
            if request is None:
                return HRResult.fail("La solicitud no existe", "NOT_FOUND",
                                     operation_id=operation_id)
            try:
                request.cancel()
            except HRDomainError as exc:
                return HRResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.leaves.update(request)
            uow.audit.record(action="LEAVE_CANCELLED", actor_user_id=actor_user_id,
                             entity_type="leave", entity_id=leave_id, detail="",
                             operation_id=operation_id)
        return HRResult.ok("Solicitud cancelada", entity_id=leave_id,
                           operation_id=operation_id)

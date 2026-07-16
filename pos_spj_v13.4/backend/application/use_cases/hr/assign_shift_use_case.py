"""Assign configurable HR work shifts to employees."""

from __future__ import annotations

from backend.application.commands.hr_commands import AssignShiftCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.entities import ShiftAssignment
from backend.domain.hr.exceptions import EmployeeInactiveError, EmployeeNotFoundError
from backend.domain.hr.repository_ports import EmployeeRepositoryPort, WorkShiftRepositoryPort
from backend.shared.events import EventBus, create_domain_event
from backend.shared.events.event_names import EventName


class AssignShiftUseCase(BaseUseCase[AssignShiftCommand]):
    name = "AssignShiftUseCase"

    def __init__(self, work_shift_repository: WorkShiftRepositoryPort, employee_repository: EmployeeRepositoryPort, *, event_bus: EventBus | None = None, permission_checker: PermissionChecker | None = None, audit_sink: HRAuditSink | None = None) -> None:
        self._work_shift_repository = work_shift_repository
        self._employee_repository = employee_repository
        self._event_bus = event_bus
        self._authorizer = HRPermissionAuthorizer(permission_checker)
        self._audit_sink = audit_sink

    def execute(self, command: AssignShiftCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.shift.manage")
        employee = self._employee_repository.get(command.employee_id)
        if employee is None:
            raise EmployeeNotFoundError(command.employee_id)
        if not employee.active:
            raise EmployeeInactiveError(command.employee_id)
        assignment = ShiftAssignment(employee_id=command.employee_id, work_shift_id=command.work_shift_id, effective_from=command.effective_from, effective_to=command.effective_to, weekdays=command.weekdays, branch_id=command.branch_id)
        self._work_shift_repository.assign(assignment)
        event = create_domain_event(event_name=EventName.WORK_SHIFT_ASSIGNED, operation_id=command.operation_id, entity_id=assignment.id, branch_id=assignment.branch_id, user_id=command.user_id, user_name=command.user_name, source_module="HR", payload={"employee_id": assignment.employee_id, "work_shift_id": assignment.work_shift_id})
        if self._event_bus is not None:
            self._event_bus.publish(event)
        record_hr_audit(self._audit_sink, action="WORK_SHIFT_ASSIGNED", operation_id=command.operation_id, entity_id=assignment.id, actor_user_id=command.user_id, branch_id=assignment.branch_id, metadata={"employee_id": assignment.employee_id, "work_shift_id": assignment.work_shift_id})
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=assignment.id, events=(event,))

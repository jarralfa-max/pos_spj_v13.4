"""Request HR leave through canonical UseCase flow."""

from __future__ import annotations

from backend.application.commands.hr_commands import RequestLeaveCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.entities import LeaveRequest
from backend.domain.hr.enums import LeaveStatus, LeaveType
from backend.domain.hr.exceptions import EmployeeInactiveError, EmployeeNotFoundError
from backend.domain.hr.policies.leave_policy import LeavePolicy
from backend.domain.hr.repository_ports import EmployeeRepositoryPort, LeaveRepositoryPort
from backend.shared.events import EventBus, create_domain_event
from backend.shared.events.event_names import EventName


class RequestLeaveUseCase(BaseUseCase[RequestLeaveCommand]):
    name = "RequestLeaveUseCase"

    def __init__(self, leave_repository: LeaveRepositoryPort, employee_repository: EmployeeRepositoryPort, *, event_bus: EventBus | None = None, permission_checker: PermissionChecker | None = None, audit_sink: HRAuditSink | None = None, policy: LeavePolicy | None = None) -> None:
        self._leave_repository = leave_repository
        self._employee_repository = employee_repository
        self._event_bus = event_bus
        self._authorizer = HRPermissionAuthorizer(permission_checker)
        self._audit_sink = audit_sink
        self._policy = policy or LeavePolicy()

    def execute(self, command: RequestLeaveCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.leave.request")
        existing = self._leave_repository.get_by_operation_id(command.operation_id)
        if existing is not None:
            return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=existing.id, message="Solicitud de permiso ya registrada.")
        employee = self._employee_repository.get(command.employee_id)
        if employee is None:
            raise EmployeeNotFoundError(command.employee_id)
        if not employee.active:
            raise EmployeeInactiveError(command.employee_id)
        requested_days = self._policy.requested_days(command.start_date, command.end_date)
        overlaps = self._leave_repository.list_overlapping(
            employee_id=command.employee_id,
            start_date=command.start_date,
            end_date=command.end_date,
            statuses=(LeaveStatus.PENDING, LeaveStatus.APPROVED),
        )
        self._policy.ensure_no_overlap(command.start_date, command.end_date, [(item.start_date, item.end_date) for item in overlaps])
        if command.leave_type == LeaveType.VACATION:
            available = self._leave_repository.get_available_days(employee_id=employee.id, branch_id=command.branch_id, leave_type=command.leave_type)
            self._policy.ensure_balance(available, requested_days)
        leave_request = LeaveRequest(
            employee_id=employee.id,
            branch_id=command.branch_id,
            leave_type=command.leave_type,
            start_date=command.start_date,
            end_date=command.end_date,
            requested_days=requested_days,
            reason=command.reason.strip(),
            status=LeaveStatus.PENDING,
            requested_by_user_id=command.user_id or "",
            operation_id=command.operation_id,
        )
        self._leave_repository.save(leave_request)
        self._leave_repository.add_history(leave_request_id=leave_request.id, previous_status=None, new_status=leave_request.status, actor_user_id=command.user_id, reason=leave_request.reason, operation_id=command.operation_id)
        event = create_domain_event(event_name=EventName.LEAVE_REQUESTED, operation_id=command.operation_id, entity_id=leave_request.id, branch_id=leave_request.branch_id, user_id=command.user_id, user_name=command.user_name, source_module="HR", payload={"employee_id": leave_request.employee_id, "leave_type": leave_request.leave_type.value})
        if self._event_bus is not None:
            self._event_bus.publish(event)
        record_hr_audit(self._audit_sink, action="LEAVE_REQUESTED", operation_id=command.operation_id, entity_id=leave_request.id, actor_user_id=command.user_id, branch_id=leave_request.branch_id, metadata={"employee_id": leave_request.employee_id, "days": str(leave_request.requested_days)})
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=leave_request.id, events=(event,))

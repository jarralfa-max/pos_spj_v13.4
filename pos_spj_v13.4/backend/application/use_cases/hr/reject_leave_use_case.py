"""Reject HR leave requests."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.application.commands.hr_commands import RejectLeaveCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.enums import LeaveStatus
from backend.domain.hr.repository_ports import LeaveRepositoryPort
from backend.shared.events import EventBus, create_domain_event
from backend.shared.events.event_names import EventName


class RejectLeaveUseCase(BaseUseCase[RejectLeaveCommand]):
    name = "RejectLeaveUseCase"

    def __init__(self, leave_repository: LeaveRepositoryPort, *, event_bus: EventBus | None = None, permission_checker: PermissionChecker | None = None, audit_sink: HRAuditSink | None = None) -> None:
        self._leave_repository = leave_repository
        self._event_bus = event_bus
        self._authorizer = HRPermissionAuthorizer(permission_checker)
        self._audit_sink = audit_sink

    def execute(self, command: RejectLeaveCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.leave.approve")
        leave_request = self._leave_repository.get(command.leave_request_id)
        if leave_request is None:
            raise ValueError("leave request not found")
        previous = leave_request.status
        if previous != LeaveStatus.PENDING:
            raise ValueError("only pending leave requests can be rejected")
        leave_request.status = LeaveStatus.REJECTED
        leave_request.updated_at = datetime.now(UTC)
        self._leave_repository.update(leave_request)
        self._leave_repository.add_history(leave_request_id=leave_request.id, previous_status=previous, new_status=leave_request.status, actor_user_id=command.user_id, reason=command.reason.strip(), operation_id=command.operation_id)
        event = create_domain_event(event_name=EventName.LEAVE_REJECTED, operation_id=command.operation_id, entity_id=leave_request.id, branch_id=leave_request.branch_id, user_id=command.user_id, user_name=command.user_name, source_module="HR", payload={"employee_id": leave_request.employee_id, "reason": command.reason.strip()})
        if self._event_bus is not None:
            self._event_bus.publish(event)
        record_hr_audit(self._audit_sink, action="LEAVE_REJECTED", operation_id=command.operation_id, entity_id=leave_request.id, actor_user_id=command.user_id, branch_id=leave_request.branch_id, metadata={"employee_id": leave_request.employee_id, "reason": command.reason.strip()})
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=leave_request.id, events=(event,))

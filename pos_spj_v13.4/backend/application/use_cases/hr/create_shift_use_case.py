"""Create configurable HR work shifts."""

from __future__ import annotations

from backend.application.commands.hr_commands import CreateShiftCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.entities import WorkShift
from backend.domain.hr.repository_ports import WorkShiftRepositoryPort
from backend.shared.events import EventBus, create_domain_event
from backend.shared.events.event_names import EventName


class CreateShiftUseCase(BaseUseCase[CreateShiftCommand]):
    name = "CreateShiftUseCase"

    def __init__(self, work_shift_repository: WorkShiftRepositoryPort, *, event_bus: EventBus | None = None, permission_checker: PermissionChecker | None = None, audit_sink: HRAuditSink | None = None) -> None:
        self._repository = work_shift_repository
        self._event_bus = event_bus
        self._authorizer = HRPermissionAuthorizer(permission_checker)
        self._audit_sink = audit_sink

    def execute(self, command: CreateShiftCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.shift.manage")
        shift = WorkShift(
            name=command.name.strip(),
            start_time=command.start_time,
            end_time=command.end_time,
            crosses_midnight=command.crosses_midnight,
            break_minutes=command.break_minutes,
            late_tolerance_minutes=command.late_tolerance_minutes,
            branch_id=command.branch_id,
        )
        self._repository.save(shift)
        event = create_domain_event(event_name=EventName.WORK_SHIFT_CREATED, operation_id=command.operation_id, entity_id=shift.id, branch_id=shift.branch_id, user_id=command.user_id, user_name=command.user_name, source_module="HR", payload={"name": shift.name})
        if self._event_bus is not None:
            self._event_bus.publish(event)
        record_hr_audit(self._audit_sink, action="WORK_SHIFT_CREATED", operation_id=command.operation_id, entity_id=shift.id, actor_user_id=command.user_id, branch_id=shift.branch_id, metadata={"name": shift.name})
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=shift.id, events=(event,))

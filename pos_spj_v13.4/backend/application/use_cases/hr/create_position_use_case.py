"""Create HR position use case."""

from __future__ import annotations

from backend.application.commands.hr_commands import CreatePositionCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.entities import Position
from backend.domain.hr.repository_ports import PositionRepositoryPort
from backend.shared.events import EventBus, create_domain_event
from backend.shared.events.event_names import EventName


class CreatePositionUseCase(BaseUseCase[CreatePositionCommand]):
    name = "CreatePositionUseCase"

    def __init__(self, position_repository: PositionRepositoryPort, *, event_bus: EventBus | None = None, permission_checker: PermissionChecker | None = None, audit_sink: HRAuditSink | None = None) -> None:
        self._position_repository = position_repository
        self._event_bus = event_bus
        self._authorizer = HRPermissionAuthorizer(permission_checker)
        self._audit_sink = audit_sink

    def execute(self, command: CreatePositionCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.settings.manage")
        position = Position(name=command.name.strip(), department_id=command.department_id)
        self._position_repository.save(position)
        event = create_domain_event(event_name=EventName.HR_CATALOG_UPDATED, operation_id=command.operation_id, entity_id=position.id, branch_id=command.branch_id, user_id=command.user_id, user_name=command.user_name, source_module="HR", payload={"catalog": "positions", "name": position.name})
        if self._event_bus is not None:
            self._event_bus.publish(event)
        record_hr_audit(
            self._audit_sink,
            action="HR_CATALOG_UPDATED",
            operation_id=command.operation_id,
            entity_id=position.id,
            actor_user_id=command.user_id,
            branch_id=command.branch_id,
            metadata={"catalog": "positions", "name": position.name},
        )
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=position.id, events=(event,))

"""Create HR department use case."""

from __future__ import annotations

from backend.application.commands.hr_commands import CreateDepartmentCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.entities import Department
from backend.domain.hr.repository_ports import DepartmentRepositoryPort
from backend.shared.events import EventBus, create_domain_event
from backend.shared.events.event_names import EventName


class CreateDepartmentUseCase(BaseUseCase[CreateDepartmentCommand]):
    name = "CreateDepartmentUseCase"

    def __init__(self, department_repository: DepartmentRepositoryPort, *, event_bus: EventBus | None = None, permission_checker: PermissionChecker | None = None, audit_sink: HRAuditSink | None = None) -> None:
        self._department_repository = department_repository
        self._event_bus = event_bus
        self._authorizer = HRPermissionAuthorizer(permission_checker)
        self._audit_sink = audit_sink

    def execute(self, command: CreateDepartmentCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.settings.manage")
        department = Department(name=command.name.strip(), branch_id=command.branch_id)
        self._department_repository.save(department)
        event = create_domain_event(event_name=EventName.HR_CATALOG_UPDATED, operation_id=command.operation_id, entity_id=department.id, branch_id=department.branch_id, user_id=command.user_id, user_name=command.user_name, source_module="HR", payload={"catalog": "departments", "name": department.name})
        if self._event_bus is not None:
            self._event_bus.publish(event)
        record_hr_audit(
            self._audit_sink,
            action="HR_CATALOG_UPDATED",
            operation_id=command.operation_id,
            entity_id=department.id,
            actor_user_id=command.user_id,
            branch_id=department.branch_id,
            metadata={"catalog": "departments", "name": department.name},
        )
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=department.id, events=(event,))

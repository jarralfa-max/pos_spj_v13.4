"""Deactivate employee use case for canonical HR."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.application.commands.hr_commands import DeactivateEmployeeCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.enums import EmploymentStatus
from backend.domain.hr.exceptions import EmployeeNotFoundError
from backend.domain.hr.repository_ports import EmployeeRepositoryPort
from backend.shared.events import EventBus, create_domain_event
from backend.shared.events.event_names import EventName


class DeactivateEmployeeUseCase(BaseUseCase[DeactivateEmployeeCommand]):
    name = "DeactivateEmployeeUseCase"

    def __init__(
        self,
        employee_repository: EmployeeRepositoryPort,
        *,
        event_bus: EventBus | None = None,
        permission_checker: PermissionChecker | None = None,
        audit_sink: HRAuditSink | None = None,
    ) -> None:
        self._employee_repository = employee_repository
        self._event_bus = event_bus
        self._authorizer = HRPermissionAuthorizer(permission_checker)
        self._audit_sink = audit_sink

    def execute(self, command: DeactivateEmployeeCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.employee.deactivate")
        employee = self._employee_repository.get(command.employee_id)
        if employee is None:
            raise EmployeeNotFoundError(command.employee_id)
        employee.active = False
        employee.employment_status = EmploymentStatus.TERMINATED
        employee.termination_date = command.termination_date
        employee.termination_reason = command.termination_reason
        employee.updated_at = datetime.now(UTC)
        self._employee_repository.save(employee)
        event = create_domain_event(
            event_name=EventName.EMPLOYEE_DEACTIVATED,
            operation_id=command.operation_id,
            entity_id=employee.id,
            branch_id=employee.branch_id,
            user_id=command.user_id,
            user_name=command.user_name,
            source_module="HR",
            payload={"termination_reason": command.termination_reason},
        )
        if self._event_bus is not None:
            self._event_bus.publish(event)
        record_hr_audit(
            self._audit_sink,
            action="HR_EMPLOYEE_DEACTIVATED",
            operation_id=command.operation_id,
            entity_id=employee.id,
            actor_user_id=command.user_id,
            branch_id=employee.branch_id,
            metadata={"termination_reason": command.termination_reason},
        )
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=employee.id, message="Empleado desactivado correctamente.", events=(event,))

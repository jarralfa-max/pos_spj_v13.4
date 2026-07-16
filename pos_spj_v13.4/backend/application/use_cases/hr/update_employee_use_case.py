"""Update employee use case for canonical HR."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.application.commands.hr_commands import UpdateEmployeeCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.exceptions import EmployeeNotFoundError
from backend.domain.hr.repository_ports import EmployeeRepositoryPort
from backend.shared.events import EventBus, create_domain_event
from backend.shared.events.event_names import EventName


class UpdateEmployeeUseCase(BaseUseCase[UpdateEmployeeCommand]):
    name = "UpdateEmployeeUseCase"

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

    def execute(self, command: UpdateEmployeeCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.employee.update")
        employee = self._employee_repository.get(command.employee_id)
        if employee is None:
            raise EmployeeNotFoundError(command.employee_id)
        employee.employee_code = command.employee_code
        employee.first_name = command.first_name
        employee.last_name = command.last_name
        employee.phone_e164 = command.phone_e164
        employee.email = command.email
        employee.branch_id = command.branch_id
        employee.department_id = command.department_id
        employee.position_id = command.position_id
        employee.supervisor_employee_id = command.supervisor_employee_id
        employee.contract_type = command.contract_type
        employee.payment_frequency = command.payment_frequency
        employee.base_salary = command.base_salary
        employee.daily_salary = command.daily_salary
        employee.hire_date = command.hire_date  # type: ignore[assignment]
        employee.bank_account_reference = command.bank_account_reference
        employee.tax_identifier = command.tax_identifier
        employee.emergency_contact_name = command.emergency_contact_name
        employee.emergency_contact_phone = command.emergency_contact_phone
        employee.updated_at = datetime.now(UTC)
        self._employee_repository.save(employee)
        event = create_domain_event(
            event_name=EventName.EMPLOYEE_UPDATED,
            operation_id=command.operation_id,
            entity_id=employee.id,
            branch_id=employee.branch_id,
            user_id=command.user_id,
            user_name=command.user_name,
            source_module="HR",
            payload={"employee_code": employee.employee_code},
        )
        if self._event_bus is not None:
            self._event_bus.publish(event)
        record_hr_audit(
            self._audit_sink,
            action="HR_EMPLOYEE_UPDATED",
            operation_id=command.operation_id,
            entity_id=employee.id,
            actor_user_id=command.user_id,
            branch_id=employee.branch_id,
            metadata={"employee_code": employee.employee_code},
        )
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=employee.id, message="Empleado actualizado correctamente.", events=(event,))

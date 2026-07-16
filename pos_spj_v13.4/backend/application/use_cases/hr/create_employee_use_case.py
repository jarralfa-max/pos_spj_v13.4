"""Create employee use case for canonical HR."""

from __future__ import annotations

from backend.application.commands.hr_commands import CreateEmployeeCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.entities import Employee
from backend.domain.hr.repository_ports import EmployeeRepositoryPort
from backend.shared.events import EventBus, create_domain_event
from backend.shared.events.event_names import EventName


class CreateEmployeeUseCase(BaseUseCase[CreateEmployeeCommand]):
    name = "CreateEmployeeUseCase"

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

    def execute(self, command: CreateEmployeeCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.employee.create")
        employee = Employee(
            employee_code=command.employee_code,
            first_name=command.first_name,
            last_name=command.last_name,
            phone_e164=command.phone_e164,
            email=command.email,
            branch_id=command.branch_id,
            department_id=command.department_id,
            position_id=command.position_id,
            supervisor_employee_id=command.supervisor_employee_id,
            contract_type=command.contract_type,
            payment_frequency=command.payment_frequency,
            base_salary=command.base_salary,
            daily_salary=command.daily_salary,
            hire_date=command.hire_date,  # type: ignore[arg-type]
            bank_account_reference=command.bank_account_reference,
            tax_identifier=command.tax_identifier,
            emergency_contact_name=command.emergency_contact_name,
            emergency_contact_phone=command.emergency_contact_phone,
        )
        self._employee_repository.save(employee)
        event = create_domain_event(
            event_name=EventName.EMPLOYEE_CREATED,
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
            action="HR_EMPLOYEE_CREATED",
            operation_id=command.operation_id,
            entity_id=employee.id,
            actor_user_id=command.user_id,
            branch_id=employee.branch_id,
            metadata={"employee_code": employee.employee_code},
        )
        return UseCaseResult(
            success=True,
            operation_id=command.operation_id,
            entity_id=employee.id,
            message="Empleado creado correctamente.",
            events=(event,),
        )

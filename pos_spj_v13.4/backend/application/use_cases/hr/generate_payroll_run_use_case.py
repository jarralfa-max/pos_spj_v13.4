"""Generate canonical payroll runs."""

from __future__ import annotations

from decimal import Decimal

from backend.application.commands.hr_commands import GeneratePayrollRunCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.entities import PayrollConcept, PayrollLine, PayrollRun
from backend.domain.hr.enums import PayrollConceptCode, PayrollRunStatus
from backend.domain.hr.exceptions import EmployeeInactiveError, EmployeeNotFoundError
from backend.domain.hr.repository_ports import EmployeeRepositoryPort, PayrollRepositoryPort
from backend.domain.hr.services.payroll_calculator import PayrollCalculator
from backend.shared.events import EventBus, create_domain_event
from backend.shared.events.event_names import EventName


class GeneratePayrollRunUseCase(BaseUseCase[GeneratePayrollRunCommand]):
    name = "GeneratePayrollRunUseCase"

    def __init__(self, payroll_repository: PayrollRepositoryPort, employee_repository: EmployeeRepositoryPort, *, event_bus: EventBus | None = None, permission_checker: PermissionChecker | None = None, audit_sink: HRAuditSink | None = None, calculator: PayrollCalculator | None = None) -> None:
        self._payroll_repository = payroll_repository
        self._employee_repository = employee_repository
        self._event_bus = event_bus
        self._authorizer = HRPermissionAuthorizer(permission_checker)
        self._audit_sink = audit_sink
        self._calculator = calculator or PayrollCalculator()

    def execute(self, command: GeneratePayrollRunCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.payroll.generate")
        existing = self._payroll_repository.get_run_by_operation_id(command.operation_id)
        if existing is not None:
            return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=existing.id, message="Corrida de nómina ya generada.")
        payroll_run = PayrollRun(branch_id=command.branch_id, period_start=command.period_start, period_end=command.period_end, operation_id=command.operation_id, status=PayrollRunStatus.CALCULATED)
        gross_total = Decimal("0")
        deduction_total = Decimal("0")
        line_items: list[PayrollLine] = []
        concept_items: list[PayrollConcept] = []
        for employee_id in command.employee_ids:
            employee = self._employee_repository.get(employee_id)
            if employee is None:
                raise EmployeeNotFoundError(employee_id)
            if not employee.active:
                raise EmployeeInactiveError(employee_id)
            gross = self._calculator.gross_salary_for_period(employee, command.period_start, command.period_end)
            deductions = Decimal("0")
            net = self._calculator.net_amount(gross, deductions)
            line = PayrollLine(payroll_run_id=payroll_run.id, employee_id=employee.id, gross_amount=gross, deductions_amount=deductions, net_amount=net)
            concept = PayrollConcept(payroll_line_id=line.id, concept_code=PayrollConceptCode.BASE_SALARY, amount=gross, notes="Sueldo base del periodo")
            gross_total += gross
            deduction_total += deductions
            line_items.append(line)
            concept_items.append(concept)
        payroll_run.gross_amount = gross_total
        payroll_run.deductions_amount = deduction_total
        payroll_run.net_amount = self._calculator.net_amount(gross_total, deduction_total)
        self._payroll_repository.save_run(payroll_run)
        for line in line_items:
            self._payroll_repository.save_line(line)
        for concept in concept_items:
            self._payroll_repository.save_concept(concept)
        event = create_domain_event(event_name=EventName.PAYROLL_RUN_GENERATED, operation_id=command.operation_id, entity_id=payroll_run.id, branch_id=payroll_run.branch_id, user_id=command.user_id, user_name=command.user_name, source_module="HR", payload={"employee_ids": list(command.employee_ids), "net_amount": str(payroll_run.net_amount)})
        if self._event_bus is not None:
            self._event_bus.publish(event)
        record_hr_audit(self._audit_sink, action="PAYROLL_RUN_GENERATED", operation_id=command.operation_id, entity_id=payroll_run.id, actor_user_id=command.user_id, branch_id=payroll_run.branch_id, metadata={"employee_ids": list(command.employee_ids), "net_amount": str(payroll_run.net_amount)})
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=payroll_run.id, events=(event,), data={"net_amount": str(payroll_run.net_amount)})

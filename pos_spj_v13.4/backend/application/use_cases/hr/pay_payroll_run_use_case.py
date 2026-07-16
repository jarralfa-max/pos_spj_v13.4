"""Pay canonical payroll runs exactly once."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.application.commands.hr_commands import PayPayrollRunCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.entities import PayrollPayment
from backend.domain.hr.enums import PayrollRunStatus
from backend.domain.hr.exceptions import PayrollAlreadyPaidError
from backend.domain.hr.policies.payroll_policy import PayrollPolicy
from backend.domain.hr.repository_ports import PayrollPaymentRepositoryPort, PayrollRepositoryPort
from backend.shared.events import EventBus, create_domain_event
from backend.shared.events.event_names import EventName


class PayPayrollRunUseCase(BaseUseCase[PayPayrollRunCommand]):
    name = "PayPayrollRunUseCase"

    def __init__(self, payroll_repository: PayrollRepositoryPort, payroll_payment_repository: PayrollPaymentRepositoryPort, *, event_bus: EventBus | None = None, permission_checker: PermissionChecker | None = None, audit_sink: HRAuditSink | None = None, policy: PayrollPolicy | None = None) -> None:
        self._payroll_repository = payroll_repository
        self._payment_repository = payroll_payment_repository
        self._event_bus = event_bus
        self._authorizer = HRPermissionAuthorizer(permission_checker)
        self._audit_sink = audit_sink
        self._policy = policy or PayrollPolicy()

    def execute(self, command: PayPayrollRunCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.payroll.pay")
        idempotent_payment = self._payment_repository.get_by_operation_id(command.operation_id)
        if idempotent_payment is not None:
            return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=idempotent_payment.id, message="Pago de nómina ya registrado.")
        payroll_run = self._payroll_repository.get_run(command.payroll_run_id)
        if payroll_run is None:
            raise ValueError("payroll run not found")
        existing_payment = self._payment_repository.get_by_run_id(payroll_run.id)
        if existing_payment is not None:
            raise PayrollAlreadyPaidError("payroll run is already paid")
        self._policy.ensure_can_pay(payroll_run.status)
        payment = PayrollPayment(payroll_run_id=payroll_run.id, branch_id=payroll_run.branch_id, payment_method=command.payment_method.strip().upper(), net_amount=payroll_run.net_amount, operation_id=command.operation_id, paid_by_user_id=command.user_id or "")
        self._payment_repository.save(payment)
        payroll_run.status = PayrollRunStatus.PAID
        payroll_run.paid_at = payment.paid_at
        payroll_run.updated_at = datetime.now(UTC)
        self._payroll_repository.update_run(payroll_run)
        employee_ids = [line.employee_id for line in self._payroll_repository.list_lines(payroll_run.id)]
        event = create_domain_event(
            event_name=EventName.PAYROLL_PAID,
            operation_id=command.operation_id,
            entity_id=payment.id,
            branch_id=payroll_run.branch_id,
            user_id=command.user_id,
            user_name=command.user_name,
            source_module="HR",
            payload={
                "payroll_payment_id": payment.id,
                "payroll_run_id": payroll_run.id,
                "branch_id": payroll_run.branch_id,
                "employee_ids": employee_ids,
                "gross_amount": str(payroll_run.gross_amount),
                "deductions_amount": str(payroll_run.deductions_amount),
                "net_amount": str(payroll_run.net_amount),
                "payment_method": payment.payment_method,
                "paid_at": payment.paid_at.isoformat(),
                "authorized_by_user_id": payroll_run.authorized_by_user_id,
                "paid_by_user_id": payment.paid_by_user_id,
            },
        )
        if self._event_bus is not None:
            self._event_bus.publish(event)
        record_hr_audit(self._audit_sink, action="PAYROLL_PAID", operation_id=command.operation_id, entity_id=payment.id, actor_user_id=command.user_id, branch_id=payroll_run.branch_id, metadata={"payroll_run_id": payroll_run.id, "net_amount": str(payroll_run.net_amount)})
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=payment.id, events=(event,), data={"payroll_run_id": payroll_run.id})

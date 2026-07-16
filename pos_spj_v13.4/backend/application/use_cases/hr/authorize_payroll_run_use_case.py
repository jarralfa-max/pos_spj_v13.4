"""Authorize canonical payroll runs."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.application.commands.hr_commands import AuthorizePayrollRunCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.enums import PayrollRunStatus
from backend.domain.hr.policies.payroll_policy import PayrollPolicy
from backend.domain.hr.repository_ports import PayrollRepositoryPort
from backend.shared.events import EventBus, create_domain_event
from backend.shared.events.event_names import EventName


class AuthorizePayrollRunUseCase(BaseUseCase[AuthorizePayrollRunCommand]):
    name = "AuthorizePayrollRunUseCase"

    def __init__(self, payroll_repository: PayrollRepositoryPort, *, event_bus: EventBus | None = None, permission_checker: PermissionChecker | None = None, audit_sink: HRAuditSink | None = None, policy: PayrollPolicy | None = None) -> None:
        self._payroll_repository = payroll_repository
        self._event_bus = event_bus
        self._authorizer = HRPermissionAuthorizer(permission_checker)
        self._audit_sink = audit_sink
        self._policy = policy or PayrollPolicy()

    def execute(self, command: AuthorizePayrollRunCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.payroll.authorize")
        payroll_run = self._payroll_repository.get_run(command.payroll_run_id)
        if payroll_run is None:
            raise ValueError("payroll run not found")
        self._policy.ensure_can_authorize(payroll_run.status)
        payroll_run.status = PayrollRunStatus.AUTHORIZED
        payroll_run.authorized_by_user_id = command.user_id
        payroll_run.updated_at = datetime.now(UTC)
        self._payroll_repository.update_run(payroll_run)
        event = create_domain_event(event_name=EventName.PAYROLL_RUN_AUTHORIZED, operation_id=command.operation_id, entity_id=payroll_run.id, branch_id=payroll_run.branch_id, user_id=command.user_id, user_name=command.user_name, source_module="HR", payload={"net_amount": str(payroll_run.net_amount)})
        if self._event_bus is not None:
            self._event_bus.publish(event)
        record_hr_audit(self._audit_sink, action="PAYROLL_RUN_AUTHORIZED", operation_id=command.operation_id, entity_id=payroll_run.id, actor_user_id=command.user_id, branch_id=payroll_run.branch_id, metadata={"net_amount": str(payroll_run.net_amount)})
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=payroll_run.id, events=(event,))

"""Create HR payment frequency catalog item use case."""

from __future__ import annotations

from backend.application.commands.hr_commands import CreatePaymentFrequencyCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.application.use_cases.base_use_case import BaseUseCase
from backend.application.use_cases.hr.audit import HRAuditSink, record_hr_audit
from backend.application.use_cases.hr.authorization import HRPermissionAuthorizer, PermissionChecker
from backend.domain.hr.entities import PaymentFrequencyCatalogItem
from backend.domain.hr.repository_ports import PaymentFrequencyRepositoryPort
from backend.shared.events import EventBus, create_domain_event
from backend.shared.events.event_names import EventName


class CreatePaymentFrequencyUseCase(BaseUseCase[CreatePaymentFrequencyCommand]):
    name = "CreatePaymentFrequencyUseCase"

    def __init__(self, repository: PaymentFrequencyRepositoryPort, *, event_bus: EventBus | None = None, permission_checker: PermissionChecker | None = None, audit_sink: HRAuditSink | None = None) -> None:
        self._repository = repository
        self._event_bus = event_bus
        self._authorizer = HRPermissionAuthorizer(permission_checker)
        self._audit_sink = audit_sink

    def execute(self, command: CreatePaymentFrequencyCommand) -> UseCaseResult:
        command.validate_context()
        self._authorizer.require(command.user_id, "hr.settings.manage")
        item = PaymentFrequencyCatalogItem(code=command.code.strip().upper(), name=command.name.strip())
        self._repository.save(item)
        event = create_domain_event(event_name=EventName.HR_CATALOG_UPDATED, operation_id=command.operation_id, entity_id=item.id, branch_id=command.branch_id, user_id=command.user_id, user_name=command.user_name, source_module="HR", payload={"catalog": "payment_frequencies", "code": item.code})
        if self._event_bus is not None:
            self._event_bus.publish(event)
        record_hr_audit(
            self._audit_sink,
            action="HR_CATALOG_UPDATED",
            operation_id=command.operation_id,
            entity_id=item.id,
            actor_user_id=command.user_id,
            branch_id=command.branch_id,
            metadata={"catalog": "payment_frequencies", "code": item.code},
        )
        return UseCaseResult(success=True, operation_id=command.operation_id, entity_id=item.id, events=(event,))

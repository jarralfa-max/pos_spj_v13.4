"""ServiceLevelPolicy administration + SLA override use cases.

Unlike CRM-5's CRMStageDefinition (which had no admin permission in CRM-2's
catalog, so that phase deliberately left CRUD unbuilt), ``SLA_MANAGE`` and
``SLA_OVERRIDE`` DO exist in CRM-2's catalog — so this phase builds their
consumers rather than leaving them orphaned.
"""

from __future__ import annotations

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.customer_service.result import CustomerServiceResult
from backend.domain.crm.exceptions import CRMDomainError
from backend.domain.customer_service.entities.service_level_policy import ServiceLevelPolicy
from backend.domain.customer_service.enums import (
    ServiceCaseChannel,
    ServiceCasePriority,
    ServiceCaseType,
)
from backend.domain.customer_service.exceptions import (
    CustomerServiceDomainError,
    InvalidSLAInstanceError,
)
from backend.infrastructure.db.repositories.customer_service.unit_of_work import (
    CustomerServiceUnitOfWork,
)


class CreateServiceLevelPolicyUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()

    def execute(
        self, connection, *, actor_user_id: str, code: str, name: str,
        first_response_minutes: int, resolution_minutes: int, operation_id: str,
        case_type: str | None = None, priority: str | None = None,
        origin_branch_id: str | None = None, channel: str | None = None,
        at_risk_threshold_pct: int = 80,
    ) -> CustomerServiceResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.SLA_MANAGE)
        except CRMDomainError as exc:
            return CustomerServiceResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerServiceUnitOfWork(connection) as uow:
            try:
                policy = ServiceLevelPolicy.create(
                    code, name, first_response_minutes, resolution_minutes,
                    case_type=ServiceCaseType(case_type) if case_type else None,
                    priority=ServiceCasePriority(priority) if priority else None,
                    origin_branch_id=origin_branch_id,
                    channel=ServiceCaseChannel(channel) if channel else None,
                    at_risk_threshold_pct=at_risk_threshold_pct)
            except (CustomerServiceDomainError, ValueError) as exc:
                return CustomerServiceResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.policies.save(policy)
        return CustomerServiceResult.ok("Política de SLA creada", entity_id=policy.id,
                                        operation_id=operation_id, code=policy.code)


class OverrideSLAUseCase:
    """A supervisor manually marks an SLA COMPLETED (e.g. resolved outside
    the normal case-resolution flow, or the deadline no longer applies) —
    always requires a reason, same accountability pattern as CRM-5's
    ``MoveOpportunityStageUseCase(override=True)``."""

    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()

    def execute(self, connection, *, actor_user_id: str, case_id: str, reason: str,
                operation_id: str) -> CustomerServiceResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.SLA_OVERRIDE)
        except CRMDomainError as exc:
            return CustomerServiceResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        if not reason.strip():
            return CustomerServiceResult.fail("Sobrescribir SLA requiere un motivo", "VALIDATION",
                                              operation_id=operation_id)
        with CustomerServiceUnitOfWork(connection) as uow:
            sla = uow.sla_instances.get_for_case(case_id)
            if sla is None:
                return CustomerServiceResult.fail("El caso no tiene una SLA asociada",
                                                  "NOT_FOUND", operation_id=operation_id)
            try:
                sla.record_resolution()
            except InvalidSLAInstanceError as exc:
                return CustomerServiceResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.sla_instances.update(sla)
            uow.audit.record(action="SLA_OVERRIDDEN", actor_user_id=actor_user_id,
                             case_id=case_id, reason=reason, operation_id=operation_id)
        return CustomerServiceResult.ok("SLA sobrescrita", entity_id=sla.id,
                                        operation_id=operation_id)

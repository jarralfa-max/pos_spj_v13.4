"""EscalateServiceCaseUseCase (§30-32): "criterios: SLA vencido, cliente
prioritario, caso crítico, reaperturas múltiples, impacto financiero,
riesgo reputacional. Registra motivo/nivel/usuario/fecha/destinatario."

The agent picks ``reason`` from the closed ``EscalationReason`` vocabulary
(recorded verbatim, not computed by a policy from inputs — see that enum's
docstring). Bumps the case's SLA escalation_level if one exists; always
transitions the case to ESCALATED regardless of whether an SLA is tracked.
"""

from __future__ import annotations

import json

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.customer_service.result import CustomerServiceResult
from backend.domain.crm.exceptions import CRMDomainError
from backend.domain.customer_service.entities.service_case_escalation import (
    ServiceCaseEscalation,
)
from backend.domain.customer_service.enums import EscalationReason
from backend.domain.customer_service.events import CustomerServiceEvents, build_event_payload
from backend.domain.customer_service.exceptions import CustomerServiceDomainError
from backend.infrastructure.db.repositories.customer_service.unit_of_work import (
    CustomerServiceUnitOfWork,
)


class EscalateServiceCaseUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()

    def execute(
        self, connection, *, actor_user_id: str, case_id: str, reason: str,
        escalated_to_user_id: str, operation_id: str, detail: str = "",
    ) -> CustomerServiceResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.CASES_ESCALATE)
        except CRMDomainError as exc:
            return CustomerServiceResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerServiceUnitOfWork(connection) as uow:
            case = uow.cases.get(case_id)
            if case is None:
                return CustomerServiceResult.fail("El caso no existe", "NOT_FOUND",
                                                  operation_id=operation_id)
            sla = uow.sla_instances.get_for_case(case_id)
            level = sla.bump_escalation() if sla is not None else 1
            try:
                reason_enum = EscalationReason(reason)
                case.escalate()
                escalation = ServiceCaseEscalation.create(
                    case.id, reason_enum, level, escalated_to_user_id, actor_user_id,
                    detail=detail)
            except (CustomerServiceDomainError, ValueError) as exc:
                return CustomerServiceResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.cases.update(case)
            if sla is not None:
                uow.sla_instances.update(sla)
            uow.escalations.save(escalation)
            uow.audit.record(action=CustomerServiceEvents.CASE_ESCALATED,
                             actor_user_id=actor_user_id, case_id=case.id,
                             reason=f"{reason_enum.value}: {detail}", operation_id=operation_id)
            payload = build_event_payload(
                CustomerServiceEvents.CASE_ESCALATED, operation_id=operation_id, case_id=case.id,
                user_id=actor_user_id, escalation_reason=reason_enum.value, level=level,
                escalated_to_user_id=escalated_to_user_id)
            uow.outbox.enqueue(payload["event_id"], CustomerServiceEvents.CASE_ESCALATED,
                               json.dumps(payload), operation_id)
        return CustomerServiceResult.ok("Caso escalado", entity_id=case_id,
                                        operation_id=operation_id, level=level)

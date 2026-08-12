"""CreateOpportunityFromLeadUseCase — the "oportunidad opcional" step §18
named but CRM-4 explicitly deferred (CRM-5 didn't exist yet at the time).
See backend/application/crm/use_cases/convert_lead_use_case.py's docstring
for the original deferral note.

Deliberately a *separate* use case rather than a change to
``ConvertLeadUseCase`` — the caller already receives ``customer_id`` back in
``ConvertLeadUseCase``'s ``CRMResult.data``, so this only needs ``lead_id``
(for ``source_lead_id``/traceability) and that ``customer_id`` explicitly.
Both use cases share the same ``connection``, so a caller that wants the
whole "convert lead → create opportunity" flow atomic can still wrap both
calls in one outer transaction (call this before committing, same shared-
connection pattern ``ConvertLeadUseCase`` already uses for its own two
bounded contexts) — but nothing here forces that; the opportunity is
genuinely optional per §18 and may be created later, by a different actor,
or not at all.

Only touches the ``crm`` schema (Opportunity's ``customer_id`` is an opaque
reference, never FK-validated against the ``customers`` schema — same
loose-coupling choice as ``Lead.origin_branch_id``/``territory_id``).
"""

from __future__ import annotations

import json

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.domain.crm.entities.opportunity import Opportunity
from backend.domain.crm.entities.opportunity_stage_history import OpportunityStageHistory
from backend.domain.crm.enums import LeadStatus
from backend.domain.crm.events import CRMEvents, build_event_payload
from backend.domain.crm.exceptions import CRMDomainError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class CreateOpportunityFromLeadUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()

    def execute(
        self, connection, *, actor_user_id: str, lead_id: str, customer_id: str,
        operation_id: str, stage_id: str | None = None, amount=None,
        expected_close_date=None, account_id: str | None = None,
    ) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.OPPORTUNITIES_CREATE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            existing = uow.opportunities.get_by_operation_id(operation_id)
            if existing is not None:
                return CRMResult.ok("Oportunidad ya registrada", entity_id=existing.id,
                                    operation_id=operation_id)
            lead = uow.leads.get(lead_id)
            if lead is None:
                return CRMResult.fail("El lead no existe", "NOT_FOUND", operation_id=operation_id)
            if lead.status is not LeadStatus.CONVERTED:
                return CRMResult.fail(
                    f"El lead debe estar convertido (está {lead.status.value})", "VALIDATION",
                    operation_id=operation_id)
            resolved_stage_id = stage_id
            if resolved_stage_id is None:
                default_stage = uow.stage_definitions.get_default_initial_stage()
                if default_stage is None:
                    return CRMResult.fail(
                        "No hay una etapa inicial configurada en el pipeline", "VALIDATION",
                        operation_id=operation_id)
                resolved_stage_id = default_stage.id
            try:
                opportunity = Opportunity.create(
                    uow.opportunities.next_code(), customer_id,
                    f"Oportunidad — {lead.display_name}", resolved_stage_id,
                    account_id=account_id, source_lead_id=lead.id,
                    owner_user_id=lead.assigned_user_id,
                    amount=amount if amount is not None else lead.estimated_value,
                    expected_close_date=(expected_close_date if expected_close_date is not None
                                         else lead.expected_purchase_date),
                    territory_id=lead.territory_id, origin_branch_id=lead.origin_branch_id,
                    created_by_user_id=actor_user_id, operation_id=operation_id)
            except (CRMDomainError, ValueError) as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.opportunities.save(opportunity, operation_id=operation_id)
            history = OpportunityStageHistory.create(
                opportunity.id, resolved_stage_id, actor_user_id,
                reason=f"oportunidad creada desde lead {lead.code}",
                probability=opportunity.probability,
                expected_close_date=opportunity.expected_close_date)
            uow.stage_history.save(history)
            uow.audit.record(
                action=CRMEvents.OPPORTUNITY_CREATED, actor_user_id=actor_user_id,
                opportunity_id=opportunity.id, reason=f"conversión de lead {lead.code}",
                after_json=json.dumps({"customer_id": customer_id, "lead_id": lead.id}),
                operation_id=operation_id)
            payload = build_event_payload(
                CRMEvents.OPPORTUNITY_CREATED, operation_id=operation_id,
                opportunity_id=opportunity.id, lead_id=lead.id, user_id=actor_user_id,
                customer_id=customer_id)
            uow.outbox.enqueue(payload["event_id"], CRMEvents.OPPORTUNITY_CREATED,
                               json.dumps(payload), operation_id)
        return CRMResult.ok("Oportunidad creada desde lead", entity_id=opportunity.id,
                            operation_id=operation_id, code=str(opportunity.code))

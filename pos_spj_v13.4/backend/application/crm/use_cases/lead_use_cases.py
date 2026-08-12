"""Lead use cases: create, assign, mark contacted, start nurturing, qualify,
disqualify, lose, archive, update.

Each: validates permission, runs in a CRMUnitOfWork, records audit and
enqueues the canonical event to the outbox. Idempotent on create
(operation_id). Mirrors
backend/application/customers/use_cases/lifecycle_use_cases.py.
"""

from __future__ import annotations

import json

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.domain.crm.entities.lead import Lead
from backend.domain.crm.entities.lead_qualification import LeadQualification
from backend.domain.crm.enums import LeadPriority, LeadSource, QualificationDecision, QualificationModel
from backend.domain.crm.events import CRMEvents, build_event_payload
from backend.domain.crm.exceptions import CRMDomainError
from backend.domain.crm.policies.duplicate_policy import LeadDuplicatePolicy
from backend.domain.crm.policies.qualification_policy import LeadQualificationPolicy
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class _BaseUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()

    def _emit(self, uow, event_name: str, lead_id: str, operation_id: str,
              actor_user_id: str, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id,
                                      lead_id=lead_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)


class CreateLeadUseCase(_BaseUseCase):
    def __init__(self, authorization=None) -> None:
        super().__init__(authorization)
        self._duplicates = LeadDuplicatePolicy()

    def execute(
        self, connection, *, actor_user_id: str, display_name: str, operation_id: str,
        company_name: str = "", contact_name: str = "", phone_e164: str | None = None,
        email: str | None = None, source: str = LeadSource.OTHER.value,
        campaign_reference_id: str | None = None, origin_branch_id: str | None = None,
        territory_id: str | None = None, priority: str = LeadPriority.NORMAL.value,
        estimated_value=None, allow_duplicate: bool = False,
    ) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.LEADS_CREATE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            existing = uow.leads.get_by_operation_id(operation_id)
            if existing is not None:
                return CRMResult.ok("Lead ya registrado", entity_id=existing.id,
                                    operation_id=operation_id)
            if not allow_duplicate:
                candidate = {"display_name": display_name, "phone_e164": phone_e164,
                             "email": email}
                matches = self._duplicates.find_matches(candidate, uow.leads.find_duplicate_rows())
                if matches:
                    return CRMResult.fail(
                        "Posible lead duplicado", "DUPLICATE", operation_id=operation_id,
                        duplicates=[{"lead_id": m.lead_id, "reasons": list(m.reasons)}
                                    for m in matches])
            try:
                lead = Lead.create(
                    uow.leads.next_code(), display_name, company_name=company_name,
                    contact_name=contact_name, phone_e164=phone_e164, email=email,
                    source=LeadSource(source), campaign_reference_id=campaign_reference_id,
                    origin_branch_id=origin_branch_id, territory_id=territory_id,
                    priority=LeadPriority(priority), estimated_value=estimated_value,
                    created_by_user_id=actor_user_id, operation_id=operation_id)
            except (CRMDomainError, ValueError) as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.leads.save(lead, operation_id=operation_id)
            uow.audit.record(action=CRMEvents.LEAD_CREATED, actor_user_id=actor_user_id,
                             lead_id=lead.id, after_json=json.dumps({"display_name": display_name}),
                             reason="alta", operation_id=operation_id)
            self._emit(uow, CRMEvents.LEAD_CREATED, lead.id, operation_id, actor_user_id)
        return CRMResult.ok("Lead creado", entity_id=lead.id, operation_id=operation_id,
                            code=str(lead.code))


class UpdateLeadUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, lead_id: str, operation_id: str,
        display_name: str | None = None, company_name: str | None = None,
        contact_name: str | None = None, next_action_at: str | None = None,
    ) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.LEADS_EDIT)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            lead = uow.leads.get(lead_id)
            if lead is None:
                return CRMResult.fail("El lead no existe", "NOT_FOUND", operation_id=operation_id)
            if display_name is not None:
                if not display_name.strip():
                    return CRMResult.fail("display_name no puede quedar vacío", "VALIDATION",
                                          operation_id=operation_id)
                lead.display_name = display_name.strip()
            if company_name is not None:
                lead.company_name = company_name
            if contact_name is not None:
                lead.contact_name = contact_name
            if next_action_at is not None:
                lead.next_action_at = next_action_at
            lead.record_edit()
            uow.leads.update(lead)
            uow.audit.record(action=CRMEvents.LEAD_UPDATED, actor_user_id=actor_user_id,
                             lead_id=lead.id, reason="edición", operation_id=operation_id)
            self._emit(uow, CRMEvents.LEAD_UPDATED, lead.id, operation_id, actor_user_id)
        return CRMResult.ok("Lead actualizado", entity_id=lead_id, operation_id=operation_id)


class _TransitionUseCase(_BaseUseCase):
    permission = ""
    event_name = ""

    def _apply(self, lead: Lead, *, actor_user_id: str, reason: str) -> None:
        raise NotImplementedError

    def execute(self, connection, *, actor_user_id: str, lead_id: str,
                operation_id: str, reason: str = "") -> CRMResult:
        try:
            self._auth.require(actor_user_id, self.permission)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            lead = uow.leads.get(lead_id)
            if lead is None:
                return CRMResult.fail("El lead no existe", "NOT_FOUND", operation_id=operation_id)
            try:
                self._apply(lead, actor_user_id=actor_user_id, reason=reason)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.leads.update(lead)
            uow.audit.record(action=self.event_name, actor_user_id=actor_user_id,
                             lead_id=lead.id, reason=reason, operation_id=operation_id)
            self._emit(uow, self.event_name, lead.id, operation_id, actor_user_id)
        return CRMResult.ok("Operación registrada", entity_id=lead_id, operation_id=operation_id)


class AssignLeadUseCase(_TransitionUseCase):
    permission = CRMPermissions.LEADS_ASSIGN
    event_name = CRMEvents.LEAD_ASSIGNED

    def execute(self, connection, *, actor_user_id: str, lead_id: str, operation_id: str,
                assignee_user_id: str, reason: str = "") -> CRMResult:
        self._assignee_user_id = assignee_user_id
        return super().execute(connection, actor_user_id=actor_user_id, lead_id=lead_id,
                               operation_id=operation_id, reason=reason)

    def _apply(self, lead, *, actor_user_id, reason):
        lead.assign(self._assignee_user_id)


class MarkLeadContactedUseCase(_TransitionUseCase):
    permission = CRMPermissions.LEADS_EDIT
    event_name = CRMEvents.LEAD_CONTACTED

    def _apply(self, lead, *, actor_user_id, reason):
        lead.mark_contacted()


class StartLeadNurturingUseCase(_TransitionUseCase):
    permission = CRMPermissions.LEADS_EDIT
    event_name = CRMEvents.LEAD_NURTURING

    def _apply(self, lead, *, actor_user_id, reason):
        lead.start_nurturing()


class DisqualifyLeadUseCase(_TransitionUseCase):
    permission = CRMPermissions.LEADS_DISQUALIFY
    event_name = CRMEvents.LEAD_DISQUALIFIED

    def _apply(self, lead, *, actor_user_id, reason):
        lead.disqualify(reason)


class LoseLeadUseCase(_TransitionUseCase):
    permission = CRMPermissions.LEADS_EDIT
    event_name = CRMEvents.LEAD_LOST

    def _apply(self, lead, *, actor_user_id, reason):
        lead.lose(reason)


class ArchiveLeadUseCase(_TransitionUseCase):
    permission = CRMPermissions.LEADS_ARCHIVE
    event_name = CRMEvents.LEAD_ARCHIVED

    def _apply(self, lead, *, actor_user_id, reason):
        lead.archive()


class QualifyLeadUseCase(_BaseUseCase):
    """Flips the lead to QUALIFIED/UNQUALIFIED *and* records the evidence
    (§17). Delegates the decision to ``LeadQualificationPolicy`` — never
    hardcodes one qualification methodology."""

    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        super().__init__(authorization)
        self._policy = LeadQualificationPolicy()

    def execute(
        self, connection, *, actor_user_id: str, lead_id: str, operation_id: str,
        model: str = QualificationModel.MANUAL.value, criteria: dict | None = None,
        score: int | None = None, score_threshold: int | None = None,
        min_criteria_passed: int | None = None,
        manual_decision: str | None = None, custom_decision: str | None = None,
        notes: str = "",
    ) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.LEADS_QUALIFY)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            lead = uow.leads.get(lead_id)
            if lead is None:
                return CRMResult.fail("El lead no existe", "NOT_FOUND", operation_id=operation_id)
            try:
                qual_model = QualificationModel(model)
                decision = self._policy.decide(
                    qual_model, criteria=criteria, score=score,
                    score_threshold=score_threshold, min_criteria_passed=min_criteria_passed,
                    manual_decision=(QualificationDecision(manual_decision)
                                     if manual_decision else None),
                    custom_decision=(QualificationDecision(custom_decision)
                                     if custom_decision else None),
                )
                qualification = LeadQualification.create(
                    lead_id, qual_model, decision, actor_user_id, criteria=criteria,
                    notes=notes, score=score)
                if decision is QualificationDecision.QUALIFIED:
                    lead.qualify()
                else:
                    lead.disqualify(notes or "No cumple criterios de calificación")
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.leads.update(lead)
            uow.qualifications.save(qualification)
            event_name = (CRMEvents.LEAD_QUALIFIED if decision is QualificationDecision.QUALIFIED
                          else CRMEvents.LEAD_DISQUALIFIED)
            uow.audit.record(action=event_name, actor_user_id=actor_user_id, lead_id=lead.id,
                             reason=f"calificación ({qual_model.value})", operation_id=operation_id)
            self._emit(uow, event_name, lead.id, operation_id, actor_user_id,
                       qualification_id=qualification.id, model=qual_model.value)
        return CRMResult.ok(
            "Calificación registrada", entity_id=qualification.id, operation_id=operation_id,
            decision=decision.value)

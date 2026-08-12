"""Opportunity use cases: create, update, assign/reassign, hold/resume,
win/lose/cancel/reopen, move stage, add product interest.

Each: validates permission, runs in a CRMUnitOfWork, records audit and
enqueues the canonical event to the outbox. Idempotent on create
(operation_id). Mirrors
backend/application/crm/use_cases/lead_use_cases.py.
"""

from __future__ import annotations

import json
from decimal import Decimal

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.domain.crm.entities.opportunity import Opportunity
from backend.domain.crm.entities.opportunity_product_interest import OpportunityProductInterest
from backend.domain.crm.entities.opportunity_stage_history import OpportunityStageHistory
from backend.domain.crm.events import CRMEvents, build_event_payload
from backend.domain.crm.exceptions import CRMDomainError
from backend.domain.crm.policies.stage_transition_policy import CRMStageTransitionPolicy
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class _BaseUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()

    def _emit(self, uow, event_name: str, opportunity_id: str, operation_id: str,
              actor_user_id: str, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id,
                                      opportunity_id=opportunity_id, user_id=actor_user_id,
                                      **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)


class CreateOpportunityUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, customer_id: str, name: str, operation_id: str,
        stage_id: str | None = None, account_id: str | None = None,
        source_lead_id: str | None = None, owner_user_id: str | None = None, amount=None,
        probability: int = 0, expected_close_date=None, territory_id: str | None = None,
        origin_branch_id: str | None = None, description: str = "",
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
                    uow.opportunities.next_code(), customer_id, name, resolved_stage_id,
                    account_id=account_id, source_lead_id=source_lead_id,
                    owner_user_id=owner_user_id, amount=amount, probability=probability,
                    expected_close_date=expected_close_date, territory_id=territory_id,
                    origin_branch_id=origin_branch_id, description=description,
                    created_by_user_id=actor_user_id, operation_id=operation_id)
            except (CRMDomainError, ValueError) as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.opportunities.save(opportunity, operation_id=operation_id)
            history = OpportunityStageHistory.create(
                opportunity.id, resolved_stage_id, actor_user_id,
                probability=opportunity.probability,
                expected_close_date=opportunity.expected_close_date)
            uow.stage_history.save(history)
            uow.audit.record(action=CRMEvents.OPPORTUNITY_CREATED, actor_user_id=actor_user_id,
                             opportunity_id=opportunity.id,
                             after_json=json.dumps({"name": name, "customer_id": customer_id}),
                             reason="alta", operation_id=operation_id)
            self._emit(uow, CRMEvents.OPPORTUNITY_CREATED, opportunity.id, operation_id,
                      actor_user_id)
        return CRMResult.ok("Oportunidad creada", entity_id=opportunity.id,
                            operation_id=operation_id, code=str(opportunity.code))


class UpdateOpportunityUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, opportunity_id: str, operation_id: str,
        name: str | None = None, amount=None, description: str | None = None,
        territory_id: str | None = None,
    ) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.OPPORTUNITIES_EDIT)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            opportunity = uow.opportunities.get(opportunity_id)
            if opportunity is None:
                return CRMResult.fail("La oportunidad no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            if name is not None:
                if not name.strip():
                    return CRMResult.fail("name no puede quedar vacío", "VALIDATION",
                                          operation_id=operation_id)
                opportunity.name = name.strip()
            if amount is not None:
                if isinstance(amount, bool) or isinstance(amount, float):
                    return CRMResult.fail("amount debe ser Decimal, nunca float", "VALIDATION",
                                          operation_id=operation_id)
                opportunity.amount = Decimal(str(amount))
            if description is not None:
                opportunity.description = description
            if territory_id is not None:
                opportunity.territory_id = territory_id
            opportunity.record_edit()
            uow.opportunities.update(opportunity)
            uow.audit.record(action=CRMEvents.OPPORTUNITY_UPDATED, actor_user_id=actor_user_id,
                             opportunity_id=opportunity.id, reason="edición",
                             operation_id=operation_id)
            self._emit(uow, CRMEvents.OPPORTUNITY_UPDATED, opportunity.id, operation_id,
                      actor_user_id)
        return CRMResult.ok("Oportunidad actualizada", entity_id=opportunity_id,
                            operation_id=operation_id)


class AssignOpportunityUseCase(_BaseUseCase):
    """Requires OPPORTUNITIES_ASSIGN for the first assignment (no prior
    owner) and OPPORTUNITIES_REASSIGN when handing an already-owned
    opportunity to someone else — both permissions exist in CRM-2's catalog
    but CRM-4's AssignLeadUseCase only ever used the ASSIGN one; this closes
    that gap for Opportunities rather than repeating it, since
    ``CRM_ROLE_MATRIX`` (backend/application/customers/role_matrix.py)
    already grants the two permissions separately per role."""

    def execute(self, connection, *, actor_user_id: str, opportunity_id: str,
                assignee_user_id: str, operation_id: str) -> CRMResult:
        with CRMUnitOfWork(connection) as uow:
            opportunity = uow.opportunities.get(opportunity_id)
            if opportunity is None:
                return CRMResult.fail("La oportunidad no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            permission = (CRMPermissions.OPPORTUNITIES_REASSIGN if opportunity.owner_user_id
                          else CRMPermissions.OPPORTUNITIES_ASSIGN)
            try:
                self._auth.require(actor_user_id, permission)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
            try:
                opportunity.assign_owner(assignee_user_id)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.opportunities.update(opportunity)
            uow.audit.record(action=CRMEvents.OPPORTUNITY_ASSIGNED, actor_user_id=actor_user_id,
                             opportunity_id=opportunity.id, operation_id=operation_id)
            self._emit(uow, CRMEvents.OPPORTUNITY_ASSIGNED, opportunity.id, operation_id,
                      actor_user_id, assignee_user_id=assignee_user_id)
        return CRMResult.ok("Propietario asignado", entity_id=opportunity_id,
                            operation_id=operation_id)


class _TransitionUseCase(_BaseUseCase):
    permission = ""
    event_name = ""

    def _apply(self, opportunity: Opportunity, *, actor_user_id: str, reason: str) -> None:
        raise NotImplementedError

    def execute(self, connection, *, actor_user_id: str, opportunity_id: str,
                operation_id: str, reason: str = "") -> CRMResult:
        try:
            self._auth.require(actor_user_id, self.permission)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            opportunity = uow.opportunities.get(opportunity_id)
            if opportunity is None:
                return CRMResult.fail("La oportunidad no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            try:
                self._apply(uow, opportunity, actor_user_id=actor_user_id, reason=reason)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.opportunities.update(opportunity)
            uow.audit.record(action=self.event_name, actor_user_id=actor_user_id,
                             opportunity_id=opportunity.id, reason=reason,
                             operation_id=operation_id)
            self._emit(uow, self.event_name, opportunity.id, operation_id, actor_user_id)
        return CRMResult.ok("Operación registrada", entity_id=opportunity_id,
                            operation_id=operation_id)


class PutOpportunityOnHoldUseCase(_TransitionUseCase):
    permission = CRMPermissions.OPPORTUNITIES_EDIT
    event_name = CRMEvents.OPPORTUNITY_PUT_ON_HOLD

    def _apply(self, uow, opportunity, *, actor_user_id, reason):
        opportunity.put_on_hold(reason)


class ResumeOpportunityUseCase(_TransitionUseCase):
    permission = CRMPermissions.OPPORTUNITIES_EDIT
    event_name = CRMEvents.OPPORTUNITY_RESUMED

    def _apply(self, uow, opportunity, *, actor_user_id, reason):
        opportunity.resume()


class WinOpportunityUseCase(_TransitionUseCase):
    permission = CRMPermissions.OPPORTUNITIES_MARK_WON
    event_name = CRMEvents.OPPORTUNITY_WON

    def _apply(self, uow, opportunity, *, actor_user_id, reason):
        won_stage = uow.stage_definitions.get_won_stage()
        opportunity.win(won_stage_id=won_stage.id if won_stage else None)


class LoseOpportunityUseCase(_TransitionUseCase):
    permission = CRMPermissions.OPPORTUNITIES_MARK_LOST
    event_name = CRMEvents.OPPORTUNITY_LOST

    def _apply(self, uow, opportunity, *, actor_user_id, reason):
        lost_stage = uow.stage_definitions.get_lost_stage()
        opportunity.lose(reason, lost_stage_id=lost_stage.id if lost_stage else None)


class CancelOpportunityUseCase(_TransitionUseCase):
    permission = CRMPermissions.OPPORTUNITIES_EDIT
    event_name = CRMEvents.OPPORTUNITY_CANCELLED

    def _apply(self, uow, opportunity, *, actor_user_id, reason):
        opportunity.cancel(reason)


class ReopenOpportunityUseCase(_TransitionUseCase):
    permission = CRMPermissions.OPPORTUNITIES_REOPEN
    event_name = CRMEvents.OPPORTUNITY_REOPENED

    def _apply(self, uow, opportunity, *, actor_user_id, reason):
        opportunity.reopen(reason)


class MoveOpportunityStageUseCase(_BaseUseCase):
    """Kanban never confirms a stage move by drag alone (§19-22) — the UI
    must call this use case, which runs CRMStageTransitionPolicy before
    committing anything."""

    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        super().__init__(authorization)
        self._policy = CRMStageTransitionPolicy()

    def execute(
        self, connection, *, actor_user_id: str, opportunity_id: str, to_stage_id: str,
        operation_id: str, reason: str = "", probability: int | None = None,
        expected_close_date=None, override: bool = False,
    ) -> CRMResult:
        permission = (CRMPermissions.OPPORTUNITIES_OVERRIDE_STAGE if override
                      else CRMPermissions.OPPORTUNITIES_CHANGE_STAGE)
        try:
            self._auth.require(actor_user_id, permission)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            opportunity = uow.opportunities.get(opportunity_id)
            if opportunity is None:
                return CRMResult.fail("La oportunidad no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            to_stage = uow.stage_definitions.get(to_stage_id)
            if to_stage is None:
                return CRMResult.fail("La etapa destino no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            from_stage_id = opportunity.stage_id
            from_stage = uow.stage_definitions.get(from_stage_id) if from_stage_id else None
            try:
                self._policy.validate(
                    opportunity, from_stage, to_stage, reason=reason, probability=probability,
                    expected_close_date=expected_close_date,
                    # CRM-6 (Actividades) no existe todavía — hasta entonces
                    # min_activities solo puede satisfacerse con override=True.
                    activities_logged_count=0, override=override)
                opportunity.move_stage(to_stage_id, probability=probability,
                                       expected_close_date=expected_close_date)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.opportunities.update(opportunity)
            history = OpportunityStageHistory.create(
                opportunity.id, to_stage.id, actor_user_id, from_stage_id=from_stage_id,
                reason=reason, probability=opportunity.probability,
                expected_close_date=opportunity.expected_close_date)
            uow.stage_history.save(history)
            uow.audit.record(action=CRMEvents.OPPORTUNITY_STAGE_CHANGED,
                             actor_user_id=actor_user_id, opportunity_id=opportunity.id,
                             reason=reason, operation_id=operation_id)
            self._emit(uow, CRMEvents.OPPORTUNITY_STAGE_CHANGED, opportunity.id, operation_id,
                      actor_user_id, to_stage_id=to_stage.id, from_stage_id=from_stage_id)
        return CRMResult.ok("Etapa actualizada", entity_id=opportunity_id,
                            operation_id=operation_id, stage_id=to_stage_id)


class AddOpportunityProductInterestUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, opportunity_id: str, product_name: str,
        operation_id: str, quantity=1, product_reference_id: str | None = None,
        estimated_unit_price=None, notes: str = "",
    ) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.OPPORTUNITIES_EDIT)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            opportunity = uow.opportunities.get(opportunity_id)
            if opportunity is None:
                return CRMResult.fail("La oportunidad no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            try:
                interest = OpportunityProductInterest.create(
                    opportunity.id, product_name, quantity=quantity,
                    product_reference_id=product_reference_id,
                    estimated_unit_price=estimated_unit_price, notes=notes)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.product_interests.save(interest)
            uow.audit.record(action="OPPORTUNITY_PRODUCT_INTEREST_ADDED",
                             actor_user_id=actor_user_id, opportunity_id=opportunity.id,
                             reason=f"interés: {product_name}", operation_id=operation_id)
        return CRMResult.ok("Interés de producto registrado", entity_id=interest.id,
                            operation_id=operation_id)

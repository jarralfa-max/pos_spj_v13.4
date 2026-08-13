"""CustomerPortfolio use cases: create/deactivate the portfolio catalog, and
assign a customer to a portfolio (§33-36).

AssignCustomerPortfolioUseCase covers both first-assignment and reassignment
under one permission code (PORTFOLIOS_ASSIGN — see permissions.py's
docstring for why no separate "reassign" code exists here). Reassignment
(a prior PortfolioAssignment already exists for this customer) is gated by
CustomerSegregationOfDutiesPolicy.enforce_ownership_reassignment_justified,
the CRM-2 mechanism built for exactly this §73 rule ("reasignar cartera...
requiere un motivo") and left unconsumed until now.
"""

from __future__ import annotations

import json

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.result import CRMResult
from backend.domain.crm.entities.customer_portfolio import CustomerPortfolio
from backend.domain.crm.entities.portfolio_assignment import PortfolioAssignment
from backend.domain.crm.events import CRMEvents, build_event_payload
from backend.domain.crm.exceptions import CRMDomainError
from backend.domain.customers.exceptions import CustomerSegregationOfDutiesError
from backend.domain.customers.policies.segregation_of_duties_policy import (
    CustomerSegregationOfDutiesPolicy,
)
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class _BaseUseCase:
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CRMAuthorizationPolicy()


class CreateCustomerPortfolioUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, code: str, name: str,
                operation_id: str, description: str = "",
                manager_user_id: str | None = None) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.PORTFOLIOS_MANAGE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            if uow.portfolios.get_by_code(code):
                return CRMResult.fail("Ya existe una cartera con ese código", "DUPLICATE",
                                      operation_id=operation_id)
            try:
                portfolio = CustomerPortfolio.create(code, name, description=description,
                                                     manager_user_id=manager_user_id)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.portfolios.save(portfolio)
            uow.audit.record(action=CRMEvents.PORTFOLIO_CREATED, actor_user_id=actor_user_id,
                             operation_id=operation_id,
                             after_json=json.dumps({"portfolio_id": portfolio.id,
                                                    "code": portfolio.code}))
            payload = build_event_payload(CRMEvents.PORTFOLIO_CREATED, operation_id=operation_id,
                                          user_id=actor_user_id, portfolio_id=portfolio.id)
            uow.outbox.enqueue(payload["event_id"], CRMEvents.PORTFOLIO_CREATED,
                               json.dumps(payload), operation_id)
            return CRMResult.ok("Cartera creada", entity_id=portfolio.id,
                                operation_id=operation_id)


class DeactivateCustomerPortfolioUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, portfolio_id: str,
                operation_id: str) -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.PORTFOLIOS_MANAGE)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            portfolio = uow.portfolios.get(portfolio_id)
            if portfolio is None:
                return CRMResult.fail("La cartera no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            portfolio.deactivate()
            uow.portfolios.update(portfolio)
            uow.audit.record(action=CRMEvents.PORTFOLIO_DEACTIVATED, actor_user_id=actor_user_id,
                             operation_id=operation_id,
                             after_json=json.dumps({"portfolio_id": portfolio.id}))
            payload = build_event_payload(CRMEvents.PORTFOLIO_DEACTIVATED,
                                          operation_id=operation_id, user_id=actor_user_id,
                                          portfolio_id=portfolio.id)
            uow.outbox.enqueue(payload["event_id"], CRMEvents.PORTFOLIO_DEACTIVATED,
                               json.dumps(payload), operation_id)
            return CRMResult.ok("Cartera desactivada", entity_id=portfolio.id,
                                operation_id=operation_id)


class AssignCustomerPortfolioUseCase(_BaseUseCase):
    def __init__(self, authorization: CRMAuthorizationPolicy | None = None) -> None:
        super().__init__(authorization)
        self._sod = CustomerSegregationOfDutiesPolicy()

    def execute(self, connection, *, actor_user_id: str, customer_id: str, portfolio_id: str,
                operation_id: str, reason: str = "") -> CRMResult:
        try:
            self._auth.require(actor_user_id, CRMPermissions.PORTFOLIOS_ASSIGN)
        except CRMDomainError as exc:
            return CRMResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CRMUnitOfWork(connection) as uow:
            portfolio = uow.portfolios.get(portfolio_id)
            if portfolio is None:
                return CRMResult.fail("La cartera no existe", "NOT_FOUND",
                                      operation_id=operation_id)
            if not portfolio.active:
                return CRMResult.fail("La cartera está inactiva", "VALIDATION",
                                      operation_id=operation_id)

            existing = uow.portfolio_assignments.get_latest(customer_id)
            if existing is not None:
                try:
                    self._sod.enforce_ownership_reassignment_justified(reason)
                except CustomerSegregationOfDutiesError as exc:
                    return CRMResult.fail(str(exc), "SOD_VIOLATION", operation_id=operation_id)

            try:
                assignment = PortfolioAssignment.capture(
                    customer_id, portfolio_id, assigned_by_user_id=actor_user_id,
                    reason=reason, operation_id=operation_id)
            except CRMDomainError as exc:
                return CRMResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.portfolio_assignments.save(assignment, operation_id=operation_id)

            event_name = (CRMEvents.PORTFOLIO_REASSIGNED if existing
                         else CRMEvents.PORTFOLIO_ASSIGNED)
            uow.audit.record(
                action=event_name, actor_user_id=actor_user_id, reason=reason,
                operation_id=operation_id,
                before_json=json.dumps({"previous_portfolio_id":
                                        existing.portfolio_id if existing else None}),
                after_json=json.dumps({"customer_id": customer_id, "portfolio_id": portfolio_id}))
            payload = build_event_payload(event_name, operation_id=operation_id,
                                          user_id=actor_user_id, customer_id=customer_id,
                                          portfolio_id=portfolio_id)
            uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload),
                               operation_id)
            message = "Cartera reasignada" if existing else "Cartera asignada"
            return CRMResult.ok(message, entity_id=assignment.id, operation_id=operation_id)

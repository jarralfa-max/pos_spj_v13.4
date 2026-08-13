"""CustomerPortfolioQueryService (§57) — read side for CustomerPortfolio/
PortfolioAssignment. Reads only; never mutates. Flat PORTFOLIOS_VIEW
permission, same no-scope-suffix precedent as CRMActivityQueryService.
"""

from __future__ import annotations

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.permissions import CRMPermissions
from backend.domain.crm.entities.customer_portfolio import CustomerPortfolio
from backend.domain.crm.entities.portfolio_assignment import PortfolioAssignment
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


class CustomerPortfolioQueryService:
    def __init__(self, connection, authorization: CRMAuthorizationPolicy | None = None) -> None:
        self._uow = CRMUnitOfWork(connection)
        self._auth = authorization or CRMAuthorizationPolicy()

    def list_active_portfolios(self, *, actor_user_id: str) -> list[CustomerPortfolio]:
        self._auth.require(actor_user_id, CRMPermissions.PORTFOLIOS_VIEW)
        return self._uow.portfolios.list_active()

    def get_current_portfolio(self, customer_id: str, *,
                              actor_user_id: str) -> CustomerPortfolio | None:
        self._auth.require(actor_user_id, CRMPermissions.PORTFOLIOS_VIEW)
        assignment = self._uow.portfolio_assignments.get_latest(customer_id)
        if assignment is None:
            return None
        return self._uow.portfolios.get(assignment.portfolio_id)

    def list_assignment_history(self, customer_id: str, *,
                                actor_user_id: str) -> list[PortfolioAssignment]:
        self._auth.require(actor_user_id, CRMPermissions.PORTFOLIOS_VIEW)
        return self._uow.portfolio_assignments.list_for_customer(customer_id)

    def list_current_members(self, portfolio_id: str, *,
                             actor_user_id: str) -> list[PortfolioAssignment]:
        """Customers whose most recent PortfolioAssignment points at this
        portfolio — resolved in Python (one get_latest() per distinct
        customer) rather than in SQL, matching this codebase's established
        preference for simple parametrized queries over correlated
        sub-selects for "current row per group" resolution."""
        self._auth.require(actor_user_id, CRMPermissions.PORTFOLIOS_VIEW)
        candidates = self._uow.portfolio_assignments.list_for_portfolio(portfolio_id)
        current: list[PortfolioAssignment] = []
        seen_customer_ids: set[str] = set()
        for assignment in candidates:
            if assignment.customer_id in seen_customer_ids:
                continue
            seen_customer_ids.add(assignment.customer_id)
            latest = self._uow.portfolio_assignments.get_latest(assignment.customer_id)
            if latest is not None and latest.id == assignment.id:
                current.append(assignment)
        return current

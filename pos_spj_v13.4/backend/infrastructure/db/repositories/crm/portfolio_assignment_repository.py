"""PortfolioAssignmentRepository — persists PortfolioAssignment evidence
records (append-only per customer — see
backend/domain/crm/entities/portfolio_assignment.py). Mirrors
backend/infrastructure/db/repositories/crm/customer_ownership_repository.py.
"""

from __future__ import annotations

from backend.domain.crm.entities.portfolio_assignment import PortfolioAssignment
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_COLS = (
    "id, customer_id, portfolio_id, assigned_by_user_id, reason, operation_id, created_at"
)


class PortfolioAssignmentRepository(CRMRepositoryBase):
    def save(self, assignment: PortfolioAssignment, *,
             operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO portfolio_assignments ({_COLS}) VALUES (?,?,?,?,?,?,?)",
            self._params(assignment, operation_id or assignment.operation_id))

    def get_latest(self, customer_id: str) -> PortfolioAssignment | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM portfolio_assignments"
            " WHERE customer_id=? ORDER BY created_at DESC, id DESC LIMIT 1",
            (customer_id,))
        return self._hydrate(row) if row else None

    def list_for_customer(self, customer_id: str) -> list[PortfolioAssignment]:
        rows = self._query(
            f"SELECT {_COLS} FROM portfolio_assignments"
            " WHERE customer_id=? ORDER BY created_at DESC, id DESC", (customer_id,))
        return [self._hydrate(r) for r in rows]

    def list_for_portfolio(self, portfolio_id: str) -> list[PortfolioAssignment]:
        rows = self._query(
            f"SELECT {_COLS} FROM portfolio_assignments"
            " WHERE portfolio_id=? ORDER BY created_at DESC, id DESC", (portfolio_id,))
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _params(assignment: PortfolioAssignment, operation_id: str | None) -> tuple:
        return (
            assignment.id, assignment.customer_id, assignment.portfolio_id,
            assignment.assigned_by_user_id, assignment.reason, operation_id,
            assignment.created_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> PortfolioAssignment:
        return PortfolioAssignment(
            id=row["id"], customer_id=row["customer_id"], portfolio_id=row["portfolio_id"],
            assigned_by_user_id=row["assigned_by_user_id"], reason=row["reason"] or "",
            operation_id=row["operation_id"], created_at=row["created_at"],
        )

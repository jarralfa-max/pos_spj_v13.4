"""CustomerPortfolioRepository — persists the "cartera de clientes"
catalog. Mirrors
backend/infrastructure/db/repositories/crm/stage_definition_repository.py.
"""

from __future__ import annotations

from backend.domain.crm.entities.customer_portfolio import CustomerPortfolio
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_COLS = "id, code, name, description, manager_user_id, active, created_at, updated_at"


class CustomerPortfolioRepository(CRMRepositoryBase):
    def save(self, portfolio: CustomerPortfolio) -> None:
        self._execute(
            f"INSERT INTO customer_portfolios ({_COLS}) VALUES (?,?,?,?,?,?,?,?)",
            self._params(portfolio))

    def update(self, portfolio: CustomerPortfolio) -> None:
        self._execute(
            "UPDATE customer_portfolios SET name=?, description=?, manager_user_id=?,"
            " active=?, updated_at=? WHERE id=?",
            (portfolio.name, portfolio.description, portfolio.manager_user_id,
             int(portfolio.active), portfolio.updated_at, portfolio.id))

    def get(self, portfolio_id: str) -> CustomerPortfolio | None:
        row = self._query_one(f"SELECT {_COLS} FROM customer_portfolios WHERE id=?",
                              (portfolio_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> CustomerPortfolio | None:
        row = self._query_one(f"SELECT {_COLS} FROM customer_portfolios WHERE code=?",
                              (code.upper(),))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[CustomerPortfolio]:
        rows = self._query(f"SELECT {_COLS} FROM customer_portfolios"
                           " WHERE active=1 ORDER BY name ASC")
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _params(portfolio: CustomerPortfolio) -> tuple:
        return (portfolio.id, portfolio.code, portfolio.name, portfolio.description,
                portfolio.manager_user_id, int(portfolio.active), portfolio.created_at,
                portfolio.updated_at)

    @staticmethod
    def _hydrate(row: dict) -> CustomerPortfolio:
        return CustomerPortfolio(
            id=row["id"], code=row["code"], name=row["name"],
            description=row["description"] or "", manager_user_id=row["manager_user_id"],
            active=bool(row["active"]), created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

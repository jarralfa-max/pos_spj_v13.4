"""LoyaltyAccountRepository — persists/reconstructs `LoyaltyAccount` against
`loyalty_accounts`."""

from __future__ import annotations

from backend.domain.loyalty.entities.loyalty_account import LoyaltyAccount
from backend.domain.loyalty.enums import AccountStatus
from backend.infrastructure.db.repositories.loyalty.base import LoyaltyRepositoryBase


class LoyaltyAccountRepository(LoyaltyRepositoryBase):
    def save(self, account: LoyaltyAccount) -> None:
        self._execute(
            """
            INSERT INTO loyalty_accounts (
                id, customer_id, status, suspended_at, closed_at, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status,
                suspended_at=excluded.suspended_at,
                closed_at=excluded.closed_at,
                updated_at=excluded.updated_at
            """,
            (
                account.id, account.customer_id, account.status.value,
                account.suspended_at, account.closed_at,
                account.created_at, account.updated_at,
            ),
        )

    def get(self, account_id: str) -> LoyaltyAccount | None:
        row = self._query_one("SELECT * FROM loyalty_accounts WHERE id=?", (account_id,))
        return self._hydrate(row) if row else None

    def get_by_customer_id(self, customer_id: str) -> LoyaltyAccount | None:
        row = self._query_one(
            "SELECT * FROM loyalty_accounts WHERE customer_id=?", (customer_id,))
        return self._hydrate(row) if row else None

    @staticmethod
    def _hydrate(row: dict) -> LoyaltyAccount:
        return LoyaltyAccount(
            id=row["id"], customer_id=row["customer_id"],
            status=AccountStatus(row["status"]),
            suspended_at=row["suspended_at"], closed_at=row["closed_at"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

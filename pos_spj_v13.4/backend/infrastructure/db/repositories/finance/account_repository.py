"""Account repository — chart of accounts persistence."""

from __future__ import annotations

from backend.domain.finance.entities.account import Account
from backend.domain.finance.enums import AccountType, CashFlowCategory, NormalBalance
from backend.domain.finance.value_objects.account_code import AccountCode
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase

_COLUMNS = ("id, code, name, account_type, normal_balance, parent_account_id, "
            "posting_allowed, reconciliation_required, currency_code, "
            "branch_restriction_id, cash_flow_category, active, created_at, updated_at")


def _to_entity(row: dict) -> Account:
    return Account(
        id=row["id"],
        code=AccountCode(row["code"]),
        name=row["name"],
        account_type=AccountType(row["account_type"]),
        normal_balance=NormalBalance(row["normal_balance"]),
        parent_account_id=row["parent_account_id"],
        posting_allowed=bool(row["posting_allowed"]),
        reconciliation_required=bool(row["reconciliation_required"]),
        currency_code=row["currency_code"],
        branch_restriction_id=row["branch_restriction_id"],
        cash_flow_category=CashFlowCategory(row["cash_flow_category"]),
        active=bool(row["active"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class AccountRepository(FinanceRepositoryBase):
    def save(self, account: Account) -> None:
        self._execute(
            f"INSERT INTO accounts ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (account.id, str(account.code), account.name, account.account_type.value,
             account.normal_balance.value, account.parent_account_id,
             int(account.posting_allowed), int(account.reconciliation_required),
             account.currency_code, account.branch_restriction_id,
             account.cash_flow_category.value, int(account.active),
             account.created_at, account.updated_at),
        )

    def update(self, account: Account) -> None:
        self._execute(
            "UPDATE accounts SET name=?, posting_allowed=?, reconciliation_required=?,"
            " branch_restriction_id=?, cash_flow_category=?, active=?, updated_at=?"
            " WHERE id=?",
            (account.name, int(account.posting_allowed), int(account.reconciliation_required),
             account.branch_restriction_id, account.cash_flow_category.value,
             int(account.active), account.updated_at, account.id),
        )

    def get(self, account_id: str) -> Account | None:
        row = self._query_one(f"SELECT {_COLUMNS} FROM accounts WHERE id=?", (account_id,))
        return _to_entity(row) if row else None

    def get_by_code(self, code: str) -> Account | None:
        row = self._query_one(f"SELECT {_COLUMNS} FROM accounts WHERE code=?", (code,))
        return _to_entity(row) if row else None

    def list_active(self) -> list[Account]:
        rows = self._query(f"SELECT {_COLUMNS} FROM accounts WHERE active=1 ORDER BY code")
        return [_to_entity(row) for row in rows]

    def list_all(self) -> list[Account]:
        rows = self._query(f"SELECT {_COLUMNS} FROM accounts ORDER BY code")
        return [_to_entity(row) for row in rows]

"""Account repository — chart of accounts persistence.

No existe borrado: una cuenta se desactiva (§8.1).
"""

from __future__ import annotations

from backend.domain.finance.entities.account import Account
from backend.domain.finance.enums import AccountType, CashFlowCategory, NormalBalance
from backend.domain.finance.value_objects.account_code import AccountCode
from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase


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


def _mutable(account: Account) -> dict:
    return {
        "name": account.name, "account_type": account.account_type.value,
        "normal_balance": account.normal_balance.value,
        "parent_account_id": account.parent_account_id,
        "posting_allowed": int(account.posting_allowed),
        "reconciliation_required": int(account.reconciliation_required),
        "branch_restriction_id": account.branch_restriction_id,
        "cash_flow_category": account.cash_flow_category.value,
        "active": int(account.active), "updated_at": account.updated_at,
    }


class AccountRepository(FinanceRepositoryBase):
    def save(self, account: Account) -> None:
        values = {"id": account.id, "code": str(account.code),
                  "currency_code": account.currency_code, "created_at": account.created_at}
        values.update(_mutable(account))
        self._insert("accounts", values)

    def update(self, account: Account) -> None:
        self._update("accounts", _mutable(account), where="id=?", params=(account.id,))

    def get(self, account_id: str) -> Account | None:
        row = self._query_one("SELECT * FROM accounts WHERE id=?", (account_id,))
        return _to_entity(row) if row else None

    def get_by_code(self, code: str) -> Account | None:
        row = self._query_one("SELECT * FROM accounts WHERE code=?", (code,))
        return _to_entity(row) if row else None

    def list_active(self) -> list[Account]:
        return [_to_entity(r) for r in
                self._query("SELECT * FROM accounts WHERE active=1 ORDER BY code")]

    def list_all(self) -> list[Account]:
        return [_to_entity(r) for r in self._query("SELECT * FROM accounts ORDER BY code")]

    def list_children(self, parent_account_id: str) -> list[Account]:
        return [_to_entity(r) for r in self._query(
            "SELECT * FROM accounts WHERE parent_account_id=? ORDER BY code",
            (parent_account_id,))]

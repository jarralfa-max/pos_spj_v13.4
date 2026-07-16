"""Account entity — one node of the chart of accounts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.finance.enums import (
    NORMAL_BALANCE_BY_TYPE,
    AccountType,
    CashFlowCategory,
    NormalBalance,
)
from backend.domain.finance.exceptions import AccountNotPostableError, FinanceDomainError
from backend.domain.finance.value_objects.account_code import AccountCode
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Account:
    id: str
    code: AccountCode
    name: str
    account_type: AccountType
    normal_balance: NormalBalance
    parent_account_id: str | None = None
    posting_allowed: bool = True
    reconciliation_required: bool = False
    currency_code: str = "MXN"
    branch_restriction_id: str | None = None
    cash_flow_category: CashFlowCategory = CashFlowCategory.NONE
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls,
        code: str,
        name: str,
        account_type: AccountType,
        *,
        parent_account_id: str | None = None,
        posting_allowed: bool = True,
        reconciliation_required: bool = False,
        currency_code: str = "MXN",
        branch_restriction_id: str | None = None,
        cash_flow_category: CashFlowCategory = CashFlowCategory.NONE,
    ) -> "Account":
        if not name or not name.strip():
            raise FinanceDomainError("Account.name is required")
        return cls(
            id=new_uuid(),
            code=AccountCode(code),
            name=name.strip(),
            account_type=account_type,
            normal_balance=NORMAL_BALANCE_BY_TYPE[account_type],
            parent_account_id=parent_account_id,
            posting_allowed=posting_allowed,
            reconciliation_required=reconciliation_required,
            currency_code=currency_code,
            branch_restriction_id=branch_restriction_id,
            cash_flow_category=cash_flow_category,
        )

    def assert_postable(self) -> None:
        if not self.active:
            raise AccountNotPostableError(f"Account {self.code} is inactive")
        if not self.posting_allowed:
            raise AccountNotPostableError(
                f"Account {self.code} is a summary account; posting is not allowed"
            )

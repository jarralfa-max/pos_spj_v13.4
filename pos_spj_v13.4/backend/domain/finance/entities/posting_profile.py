"""PostingProfile entity — configurable account mapping for automated postings.

Handlers must never hardcode account ids: they resolve a profile by selection
criteria (instrument type, program, campaign, branch, customer type, currency,
funding party) with an effective date range, then read the role → account map.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from backend.domain.finance.enums import CommercialInstrumentType
from backend.domain.finance.exceptions import (
    FinanceDomainError,
    PostingAccountNotConfiguredError,
)
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: Account roles a profile may configure.
ACCOUNT_ROLES = (
    "liability_account_id",
    "expense_account_id",
    "contra_revenue_account_id",
    "revenue_account_id",
    "inventory_account_id",
    "cost_of_sales_account_id",
    "breakage_income_account_id",
    "customer_credit_liability_account_id",
    "gift_card_liability_account_id",
    "promotional_balance_account_id",
    "third_party_receivable_account_id",
    "clearing_account_id",
    "rounding_account_id",
    "tax_account_id",
    "receivable_account_id",
    "payable_account_id",
    "cash_account_id",
    "bank_account_id",
    "salary_expense_account_id",
    "salary_payable_account_id",
    "social_security_payable_account_id",
    "inventory_adjustment_account_id",
    "waste_expense_account_id",
    "production_wip_account_id",
    "capital_account_id",
    "asset_account_id",
    "accumulated_depreciation_account_id",
    "depreciation_expense_account_id",
    "cash_over_short_account_id",
    "discount_account_id",
)


@dataclass(slots=True)
class PostingProfile:
    id: str
    profile_key: str                 # e.g. "SALE_CASH", "LOYALTY_POINTS.DEFAULT"
    description: str
    accounts: dict[str, str]         # role → account_id (UUID)
    effective_from: date
    effective_to: date | None = None
    instrument_type: CommercialInstrumentType | None = None
    program_id: str | None = None
    campaign_id: str | None = None
    branch_id: str | None = None
    customer_type: str | None = None
    currency_code: str | None = None
    funding_party: str | None = None
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, profile_key: str, description: str, accounts: dict[str, str],
               effective_from: date, **kwargs) -> "PostingProfile":
        if not profile_key or not profile_key.strip():
            raise FinanceDomainError("PostingProfile.profile_key is required")
        for role in accounts:
            if role not in ACCOUNT_ROLES:
                raise FinanceDomainError(f"Unknown posting profile account role: {role}")
        return cls(
            id=new_uuid(), profile_key=profile_key.strip(), description=description,
            accounts=dict(accounts), effective_from=effective_from, **kwargs,
        )

    def is_effective_on(self, value: date) -> bool:
        if not self.active or value < self.effective_from:
            return False
        return self.effective_to is None or value <= self.effective_to

    def account_for(self, role: str) -> str:
        if role not in ACCOUNT_ROLES:
            raise FinanceDomainError(f"Unknown posting profile account role: {role}")
        account_id = self.accounts.get(role)
        if not account_id:
            raise PostingAccountNotConfiguredError(
                f"Posting profile {self.profile_key!r} does not configure role {role!r}"
            )
        return account_id

    def has_account(self, role: str) -> bool:
        return bool(self.accounts.get(role))

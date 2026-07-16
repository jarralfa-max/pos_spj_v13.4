"""FixedAsset entity — CAPEX, capitalization, depreciation and disposal."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.domain.finance.enums import DepreciationMethod, FixedAssetStatus
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.value_objects.money import Money
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class FixedAsset:
    id: str
    name: str
    acquisition_cost: Money
    residual_value: Money
    useful_life_months: int
    capitalization_date: date | None
    operation_id: str
    accumulated_depreciation: Money = None  # type: ignore[assignment]
    depreciation_method: DepreciationMethod = DepreciationMethod.STRAIGHT_LINE
    status: FixedAssetStatus = FixedAssetStatus.DRAFT
    asset_account_id: str | None = None
    depreciation_expense_account_id: str | None = None
    accumulated_depreciation_account_id: str | None = None
    last_depreciated_period: str | None = None   # "YYYY-MM"
    disposal_date: date | None = None
    disposal_journal_entry_id: str | None = None
    branch_id: str | None = None
    cost_center_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if self.accumulated_depreciation is None:
            self.accumulated_depreciation = Money.zero(self.acquisition_cost.currency_code)

    @classmethod
    def create(cls, name: str, acquisition_cost: Money, residual_value: Money,
               useful_life_months: int, operation_id: str, *,
               branch_id: str | None = None, cost_center_id: str | None = None) -> "FixedAsset":
        if not name or not name.strip():
            raise FinanceDomainError("FixedAsset.name is required")
        if not acquisition_cost.is_positive():
            raise FinanceDomainError("FixedAsset.acquisition_cost must be positive")
        if residual_value.is_negative() or residual_value > acquisition_cost:
            raise FinanceDomainError("FixedAsset.residual_value must be within [0, acquisition_cost]")
        if useful_life_months <= 0:
            raise FinanceDomainError("FixedAsset.useful_life_months must be positive")
        return cls(
            id=new_uuid(), name=name.strip(), acquisition_cost=acquisition_cost,
            residual_value=residual_value, useful_life_months=useful_life_months,
            capitalization_date=None, operation_id=operation_id,
            branch_id=branch_id, cost_center_id=cost_center_id,
        )

    def capitalize(self, capitalization_date: date, asset_account_id: str,
                   depreciation_expense_account_id: str,
                   accumulated_depreciation_account_id: str) -> None:
        if self.status is not FixedAssetStatus.DRAFT:
            raise FinanceDomainError(f"Cannot capitalize asset in status {self.status.value}")
        self.capitalization_date = capitalization_date
        self.asset_account_id = asset_account_id
        self.depreciation_expense_account_id = depreciation_expense_account_id
        self.accumulated_depreciation_account_id = accumulated_depreciation_account_id
        self.status = FixedAssetStatus.CAPITALIZED
        self.updated_at = _utcnow()

    def depreciable_base(self) -> Money:
        return self.acquisition_cost.subtract(self.residual_value)

    def monthly_depreciation(self) -> Money:
        base = self.depreciable_base()
        return Money(base.amount / Decimal(self.useful_life_months), base.currency_code)

    def remaining_depreciable(self) -> Money:
        return self.depreciable_base().subtract(self.accumulated_depreciation)

    def register_depreciation(self, amount: Money, period_code: str) -> None:
        if self.status is not FixedAssetStatus.CAPITALIZED:
            raise FinanceDomainError(f"Cannot depreciate asset in status {self.status.value}")
        if self.last_depreciated_period is not None and period_code <= self.last_depreciated_period:
            raise FinanceDomainError(
                f"Period {period_code} was already depreciated (last={self.last_depreciated_period})"
            )
        if amount > self.remaining_depreciable():
            raise FinanceDomainError("Depreciation exceeds the remaining depreciable base")
        self.accumulated_depreciation = self.accumulated_depreciation.add(amount)
        self.last_depreciated_period = period_code
        if self.remaining_depreciable().is_zero():
            self.status = FixedAssetStatus.FULLY_DEPRECIATED
        self.updated_at = _utcnow()

    def dispose(self, disposal_date: date, journal_entry_id: str) -> None:
        if self.status not in (FixedAssetStatus.CAPITALIZED, FixedAssetStatus.FULLY_DEPRECIATED):
            raise FinanceDomainError(f"Cannot dispose asset in status {self.status.value}")
        self.status = FixedAssetStatus.DISPOSED
        self.disposal_date = disposal_date
        self.disposal_journal_entry_id = journal_entry_id
        self.updated_at = _utcnow()

    def net_book_value(self) -> Money:
        return self.acquisition_cost.subtract(self.accumulated_depreciation)

"""DepreciationDomainService — computes and applies periodic depreciation."""

from __future__ import annotations

from backend.domain.finance.entities.fixed_asset import FixedAsset
from backend.domain.finance.enums import FixedAssetStatus
from backend.domain.finance.policies.depreciation_policy import DepreciationPolicy
from backend.domain.finance.value_objects.money import Money


class DepreciationDomainService:
    def __init__(self) -> None:
        self._policy = DepreciationPolicy()

    def compute_period_depreciation(self, asset: FixedAsset, period_code: str) -> Money:
        return self._policy.monthly_amount(asset, period_code)

    def apply(self, asset: FixedAsset, period_code: str) -> Money:
        """Compute and register one period. Returns the amount for the journal entry."""
        amount = self.compute_period_depreciation(asset, period_code)
        if amount.is_zero():
            return amount
        asset.register_depreciation(amount, period_code)
        return amount

    @staticmethod
    def depreciable_assets(assets: list[FixedAsset], period_code: str) -> list[FixedAsset]:
        return [
            asset for asset in assets
            if asset.status is FixedAssetStatus.CAPITALIZED
            and (asset.last_depreciated_period is None or asset.last_depreciated_period < period_code)
            and asset.capitalization_date is not None
            and f"{asset.capitalization_date.year:04d}-{asset.capitalization_date.month:02d}" <= period_code
        ]

"""Depreciation policy — straight-line monthly depreciation amounts."""

from __future__ import annotations

from backend.domain.finance.entities.fixed_asset import FixedAsset
from backend.domain.finance.enums import DepreciationMethod, FixedAssetStatus
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.value_objects.money import Money


class DepreciationPolicy:
    def monthly_amount(self, asset: FixedAsset, period_code: str) -> Money:
        """Amount to depreciate for one period. Never exceeds the remaining base."""
        if asset.status is not FixedAssetStatus.CAPITALIZED:
            raise FinanceDomainError(
                f"Asset {asset.name!r} is {asset.status.value}; only CAPITALIZED assets depreciate"
            )
        if asset.depreciation_method is not DepreciationMethod.STRAIGHT_LINE:
            raise FinanceDomainError(f"Unsupported depreciation method: {asset.depreciation_method}")
        if asset.last_depreciated_period is not None and period_code <= asset.last_depreciated_period:
            raise FinanceDomainError(
                f"Period {period_code} already depreciated for asset {asset.name!r}"
            )
        remaining = asset.remaining_depreciable()
        monthly = asset.monthly_depreciation()
        return monthly if monthly <= remaining else remaining

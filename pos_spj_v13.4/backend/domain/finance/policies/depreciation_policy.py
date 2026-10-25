"""Depreciation policy — straight-line monthly depreciation amounts."""

from __future__ import annotations

from backend.domain.finance.entities.fixed_asset import FixedAsset
from backend.domain.finance.enums import DepreciationMethod, FixedAssetStatus
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.value_objects.money import Money


class DepreciationPolicy:
    def monthly_amount(self, asset: FixedAsset, period_code: str) -> Money:
        """Amount to depreciate for one period. Never exceeds the remaining base."""
        if asset.status is not FixedAssetStatus.ACTIVE:
            raise FinanceDomainError(
                f"Asset {asset.name!r} is {asset.status.value}; only ACTIVE assets depreciate"
            )
        if asset.depreciation_method is not DepreciationMethod.STRAIGHT_LINE:
            raise FinanceDomainError(f"Unsupported depreciation method: {asset.depreciation_method}")
        if asset.last_depreciated_period is not None and period_code <= asset.last_depreciated_period:
            raise FinanceDomainError(
                f"Period {period_code} already depreciated for asset {asset.name!r}"
            )
        remaining = asset.remaining_depreciable()
        monthly = asset.monthly_depreciation()
        # Auditoría F19: la cuota del ÚLTIMO mes de vida útil liquida el
        # remanente (33.33 + 33.33 + 33.34 = 100 en tres meses). Antes el
        # centavo de redondeo generaba un cuarto mes que la vida útil no tiene.
        # Meses omitidos: no se recuperan a mitad de vida; el último mes (o
        # cualquiera posterior) liquida lo que falte.
        if self.life_month_index(asset, period_code) >= asset.useful_life_months:
            return remaining
        return monthly if monthly <= remaining else remaining

    @staticmethod
    def life_month_index(asset: FixedAsset, period_code: str) -> int:
        """Mes de vida útil (1 = mes de capitalización) que cae en ``period_code``."""
        if asset.capitalization_date is None:
            return 0
        year, month = (int(part) for part in period_code.split("-"))
        start = asset.capitalization_date
        return (year - start.year) * 12 + (month - start.month) + 1

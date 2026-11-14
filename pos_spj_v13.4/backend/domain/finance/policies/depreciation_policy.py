"""Depreciation policy — straight-line monthly depreciation amounts."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from backend.domain.finance.entities.fixed_asset import FixedAsset
from backend.domain.finance.enums import DepreciationMethod, FixedAssetStatus
from backend.domain.finance.exceptions import FinanceDomainError
from backend.domain.finance.value_objects.money import Money


class DepreciationPolicy:
    def monthly_amount(self, asset: FixedAsset, period_code: str) -> Money:
        """Importe a depreciar en ``period_code``: la cuota del mes más los meses
        omitidos desde la última corrida. Nunca excede la base restante."""
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
        # Los meses suspendidos no cuentan: alargan la vida en calendario.
        in_service = self.life_month_index(asset, period_code) - asset.suspended_months
        if in_service >= asset.useful_life_months:
            return remaining
        # SDLC-FIN-003 (decisión del responsable, 2026-11-05): los meses omitidos
        # se recuperan en el siguiente periodo corrido.
        due = monthly.multiply(max(in_service - self._months_covered(asset, monthly), 1))
        return due if due <= remaining else remaining

    @staticmethod
    def _months_covered(asset: FixedAsset, monthly: Money) -> int:
        """Cuotas que ya cubre la depreciación acumulada."""
        if not monthly.is_positive():
            return 0
        covered = asset.accumulated_depreciation.amount / monthly.amount
        return int(covered.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @staticmethod
    def life_month_index(asset: FixedAsset, period_code: str) -> int:
        """Mes de vida útil (1 = mes de capitalización) que cae en ``period_code``."""
        if asset.capitalization_date is None:
            return 0
        year, month = (int(part) for part in period_code.split("-"))
        start = asset.capitalization_date
        return (year - start.year) * 12 + (month - start.month) + 1

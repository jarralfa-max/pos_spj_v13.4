"""ProductQualityProfile — the quality contract a product declares (§20).

Products defines the profile (what must be checked, acceptable fat/moisture bands,
organoleptic/documentation requirements); Calidad executes the inspection and
releases or blocks. Percentage bands are Decimal (min ≤ max, 0-100).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from backend.domain.products.exceptions import InvalidQualityProfileError
from backend.shared.ids import new_uuid


def _pct(value, label: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidQualityProfileError(f"{label} no puede ser float")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidQualityProfileError(f"{label} inválido") from exc
    if not (Decimal("0") <= d <= Decimal("100")):
        raise InvalidQualityProfileError(f"{label} debe estar entre 0 y 100 %")
    return d


@dataclass
class ProductQualityProfile:
    product_id: str
    id: str = field(default_factory=new_uuid)
    inspection_required: bool = False
    temperature_required: bool = False
    weight_check_required: bool = False
    organoleptic_check_required: bool = False
    microbiological_test_required: bool = False   # future
    fat_pct_min: Decimal | None = None
    fat_pct_max: Decimal | None = None
    moisture_pct_min: Decimal | None = None
    moisture_pct_max: Decimal | None = None
    color_requirement: str | None = None
    odor_requirement: str | None = None
    packaging_requirement: str | None = None
    documentation_requirement: str | None = None
    quarantine_required: bool = False

    def __post_init__(self) -> None:
        if not self.product_id:
            raise InvalidQualityProfileError("El perfil de calidad requiere producto")
        self.fat_pct_min = _pct(self.fat_pct_min, "fat_pct_min")
        self.fat_pct_max = _pct(self.fat_pct_max, "fat_pct_max")
        self.moisture_pct_min = _pct(self.moisture_pct_min, "moisture_pct_min")
        self.moisture_pct_max = _pct(self.moisture_pct_max, "moisture_pct_max")
        self._check_band(self.fat_pct_min, self.fat_pct_max, "grasa")
        self._check_band(self.moisture_pct_min, self.moisture_pct_max, "humedad")

    @staticmethod
    def _check_band(lo: Decimal | None, hi: Decimal | None, label: str) -> None:
        if lo is not None and hi is not None and lo > hi:
            raise InvalidQualityProfileError(
                f"El rango de {label} tiene mínimo mayor que máximo")

    def fat_in_range(self, value) -> bool:
        v = _pct(value, "grasa")
        if self.fat_pct_min is not None and v < self.fat_pct_min:
            return False
        if self.fat_pct_max is not None and v > self.fat_pct_max:
            return False
        return True

"""CatchWeightConfiguration — how a product declares variable weight (§12).

Meat/poultry products are counted in pieces but priced/stocked by real weight.
This value object is the *definition* a product carries: the nominal (logistic)
unit, the weight unit, the acceptable weight range, tolerance, price basis and
whether a scale barcode / label is required. Capture of the real weight lives in
Inventory (INV-8); here we only define the contract and validate a reading against
the declared range.

Decimal-only; float is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from backend.domain.products.exceptions import InvalidCatchWeightConfigurationError
from backend.domain.products.unit_enums import PriceBasis


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidCatchWeightConfigurationError("No se permite float en peso/tolerancia")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidCatchWeightConfigurationError(f"Valor inválido: {value!r}") from exc


@dataclass(frozen=True)
class CatchWeightConfiguration:
    enabled: bool
    nominal_unit_id: str
    weight_unit_id: str
    minimum_weight: Decimal
    maximum_weight: Decimal
    average_weight: Decimal | None = None
    tolerance_pct: Decimal = Decimal("0")
    price_basis: PriceBasis = PriceBasis.PER_KILOGRAM
    label_required: bool = True
    scale_barcode_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.enabled:
            return  # una config deshabilitada no exige rango
        if not self.nominal_unit_id or not self.weight_unit_id:
            raise InvalidCatchWeightConfigurationError(
                "El peso variable requiere unidad nominal y de peso (§12)")
        object.__setattr__(self, "minimum_weight", _dec(self.minimum_weight))
        object.__setattr__(self, "maximum_weight", _dec(self.maximum_weight))
        object.__setattr__(self, "average_weight", _dec(self.average_weight))
        object.__setattr__(self, "tolerance_pct", _dec(self.tolerance_pct))
        if self.minimum_weight is None or self.maximum_weight is None:
            raise InvalidCatchWeightConfigurationError(
                "El peso variable requiere rango mínimo y máximo (§35)")
        if self.minimum_weight < 0 or self.maximum_weight < 0:
            raise InvalidCatchWeightConfigurationError("Los pesos no pueden ser negativos")
        if self.minimum_weight > self.maximum_weight:
            raise InvalidCatchWeightConfigurationError(
                "El peso mínimo no puede exceder el máximo")
        if self.average_weight is not None and not (
                self.minimum_weight <= self.average_weight <= self.maximum_weight):
            raise InvalidCatchWeightConfigurationError(
                "El peso promedio debe estar dentro del rango")
        if not (Decimal("0") <= self.tolerance_pct <= Decimal("100")):
            raise InvalidCatchWeightConfigurationError(
                "La tolerancia debe estar entre 0 y 100 %")
        if not isinstance(self.price_basis, PriceBasis):
            try:
                object.__setattr__(self, "price_basis", PriceBasis(str(self.price_basis)))
            except ValueError as exc:
                raise InvalidCatchWeightConfigurationError(
                    f"Base de precio inválida: {self.price_basis!r}") from exc

    def is_weight_in_range(self, weight) -> bool:
        """True if a captured weight falls within [min, max] widened by tolerance."""
        if not self.enabled:
            return True
        w = _dec(weight)
        span = (self.maximum_weight - self.minimum_weight)
        margin = (span * self.tolerance_pct) / Decimal("100")
        return (self.minimum_weight - margin) <= w <= (self.maximum_weight + margin)

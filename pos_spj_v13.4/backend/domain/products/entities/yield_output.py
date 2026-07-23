"""YieldOutput — an expected output of a yield profile version (§23).

Each output declares an expected quantity and an expected yield percentage with an
optional min/max acceptance band, plus a cost-allocation weight (Products declares
the weight; Costing/Production compute the real cost). Decimal-only; the profile
never hardcodes an exact 100 % — a tolerance band is used instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from backend.domain.products.exceptions import YieldProfileInvalidError
from backend.domain.products.recipe_enums import OutputType
from backend.shared.ids import new_uuid


def _dec(value, label: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise YieldProfileInvalidError(f"{label} no puede ser float")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise YieldProfileInvalidError(f"{label} inválido: {value!r}") from exc


def _opt_pct(value, label: str) -> Decimal | None:
    if value is None:
        return None
    d = _dec(value, label)
    if not (Decimal("0") <= d <= Decimal("100")):
        raise YieldProfileInvalidError(f"{label} debe estar en [0, 100]")
    return d


@dataclass
class YieldOutput:
    product_id: str
    output_type: OutputType
    expected_yield_pct: Decimal
    unit_id: str
    id: str = field(default_factory=new_uuid)
    version_id: str | None = None
    expected_quantity: Decimal = Decimal("0")
    minimum_yield_pct: Decimal | None = None
    maximum_yield_pct: Decimal | None = None
    cost_allocation_weight: Decimal = Decimal("0")
    sequence: int = 0

    def __post_init__(self) -> None:
        if not self.product_id:
            raise YieldProfileInvalidError("El output de rendimiento requiere producto")
        if not self.unit_id:
            raise YieldProfileInvalidError("El output de rendimiento requiere unidad")
        if not isinstance(self.output_type, OutputType):
            try:
                self.output_type = OutputType(str(self.output_type))
            except ValueError as exc:
                raise YieldProfileInvalidError(
                    f"Tipo de output inválido: {self.output_type!r}") from exc
        expected = _opt_pct(self.expected_yield_pct, "expected_yield_pct")
        if expected is None:
            raise YieldProfileInvalidError("expected_yield_pct es obligatorio")
        self.expected_yield_pct = expected
        self.expected_quantity = _dec(self.expected_quantity, "expected_quantity")
        if self.expected_quantity < 0:
            raise YieldProfileInvalidError("expected_quantity no puede ser negativa")
        self.minimum_yield_pct = _opt_pct(self.minimum_yield_pct, "minimum_yield_pct")
        self.maximum_yield_pct = _opt_pct(self.maximum_yield_pct, "maximum_yield_pct")
        self.cost_allocation_weight = _dec(self.cost_allocation_weight, "cost_allocation_weight")
        if self.cost_allocation_weight < 0:
            raise YieldProfileInvalidError("cost_allocation_weight no puede ser negativa")
        self._check_band()

    def _check_band(self) -> None:
        lo, hi, exp = self.minimum_yield_pct, self.maximum_yield_pct, self.expected_yield_pct
        if lo is not None and hi is not None and lo > hi:
            raise YieldProfileInvalidError("minimum_yield_pct no puede exceder maximum_yield_pct")
        if lo is not None and exp < lo:
            raise YieldProfileInvalidError("expected_yield_pct por debajo del mínimo")
        if hi is not None and exp > hi:
            raise YieldProfileInvalidError("expected_yield_pct por encima del máximo")

    def yield_in_band(self, actual_pct) -> bool:
        a = _dec(actual_pct, "actual_pct")
        if self.minimum_yield_pct is not None and a < self.minimum_yield_pct:
            return False
        if self.maximum_yield_pct is not None and a > self.maximum_yield_pct:
            return False
        return True

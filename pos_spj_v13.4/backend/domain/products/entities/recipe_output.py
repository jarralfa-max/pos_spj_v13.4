"""RecipeOutput — an output line of a recipe version (§21, §23).

A recipe may yield several outputs: the main product plus co-/by-products, plus
theoretical waste/loss. Each output carries a Decimal expected quantity and an
optional expected yield percentage (0-100).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from backend.domain.products.exceptions import RecipeYieldInvalidError
from backend.domain.products.recipe_enums import OutputType
from backend.shared.ids import new_uuid


def _dec(value, label: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise RecipeYieldInvalidError(f"{label} no puede ser float")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RecipeYieldInvalidError(f"{label} inválido: {value!r}") from exc


@dataclass
class RecipeOutput:
    product_id: str
    output_type: OutputType
    quantity: Decimal
    unit_id: str
    id: str = field(default_factory=new_uuid)
    version_id: str | None = None
    expected_yield_pct: Decimal | None = None
    sequence: int = 0

    def __post_init__(self) -> None:
        if not self.product_id:
            raise RecipeYieldInvalidError("El output requiere producto")
        if not self.unit_id:
            raise RecipeYieldInvalidError("El output requiere unidad")
        if not isinstance(self.output_type, OutputType):
            try:
                self.output_type = OutputType(str(self.output_type))
            except ValueError as exc:
                raise RecipeYieldInvalidError(
                    f"Tipo de output inválido: {self.output_type!r}") from exc
        self.quantity = _dec(self.quantity, "quantity")
        if self.quantity < 0:
            raise RecipeYieldInvalidError("La cantidad del output no puede ser negativa")
        if self.expected_yield_pct is not None:
            self.expected_yield_pct = _dec(self.expected_yield_pct, "expected_yield_pct")
            if not (Decimal("0") <= self.expected_yield_pct <= Decimal("100")):
                raise RecipeYieldInvalidError("expected_yield_pct debe estar en [0, 100]")

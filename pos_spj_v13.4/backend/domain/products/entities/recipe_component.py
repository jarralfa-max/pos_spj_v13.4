"""RecipeComponent — an input line of a recipe version (§21).

A component consumes a product (raw material, intermediate, ingredient, packaging)
in a Decimal quantity, with an optional theoretical scrap percentage. Quantity is
strictly positive; scrap is 0-100 %.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from backend.domain.products.exceptions import InvalidRecipeError
from backend.shared.ids import new_uuid


def _dec(value, label: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidRecipeError(f"{label} no puede ser float")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidRecipeError(f"{label} inválido: {value!r}") from exc


@dataclass
class RecipeComponent:
    component_product_id: str
    quantity: Decimal
    unit_id: str
    id: str = field(default_factory=new_uuid)
    version_id: str | None = None
    scrap_pct: Decimal = Decimal("0")
    sequence: int = 0

    def __post_init__(self) -> None:
        if not self.component_product_id:
            raise InvalidRecipeError("El componente requiere producto")
        if not self.unit_id:
            raise InvalidRecipeError("El componente requiere unidad")
        self.quantity = _dec(self.quantity, "quantity")
        if self.quantity <= 0:
            raise InvalidRecipeError("La cantidad del componente debe ser positiva")
        self.scrap_pct = _dec(self.scrap_pct, "scrap_pct")
        if not (Decimal("0") <= self.scrap_pct < Decimal("100")):
            raise InvalidRecipeError("scrap_pct debe estar en [0, 100)")

    def gross_quantity(self) -> Decimal:
        """Quantity including theoretical scrap: qty / (1 - scrap%)."""
        factor = Decimal("1") - (self.scrap_pct / Decimal("100"))
        return self.quantity / factor

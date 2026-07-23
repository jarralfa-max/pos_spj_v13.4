"""RecipeExplosionService — expand a recipe version into required quantities (§21, §27).

Given a target output quantity, returns the Decimal quantity of each component
(including theoretical scrap) needed. This is the read-model Production/Sales use
to know what to consume; it performs no inventory movement. Decimal-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.products.entities.recipe_version import RecipeVersion
from backend.domain.products.exceptions import InvalidRecipeError


@dataclass(frozen=True)
class ExplodedComponent:
    component_product_id: str
    quantity: Decimal
    unit_id: str


def _dec(value) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidRecipeError("La cantidad objetivo no puede ser float")
    return Decimal(str(value))


class RecipeExplosionService:
    def explode(
        self,
        version: RecipeVersion,
        target_quantity: Decimal | int | str = Decimal("1"),
        *,
        include_scrap: bool = True,
    ) -> list[ExplodedComponent]:
        factor = _dec(target_quantity)
        if factor <= 0:
            raise InvalidRecipeError("La cantidad objetivo debe ser positiva")
        result: list[ExplodedComponent] = []
        for c in version.components:
            base = c.gross_quantity() if include_scrap else c.quantity
            result.append(ExplodedComponent(
                component_product_id=c.component_product_id,
                quantity=(base * factor),
                unit_id=c.unit_id))
        return result

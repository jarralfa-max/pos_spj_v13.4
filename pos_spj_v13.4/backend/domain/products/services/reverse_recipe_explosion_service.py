"""ReverseRecipeExplosionService — the inverse of `RecipeExplosionService`
(ERP integration master prompt §15-19, Fase 7).

`RecipeExplosionService` answers "given I want to PRODUCE this much of the
recipe's product, how much of each COMPONENT do I need" (inputs → outputs).
This service answers the opposite question for a DISASSEMBLY/CUTTING_YIELD
recipe specifically: those recipes have no `components`, only `outputs`
(whole chicken → breast/leg/wing, validated elsewhere to carry outputs
only) — so "reconstructing the base product from its parts" means reading
those SAME outputs as the recipe for how many parts one reconstructed unit
consumes. No inventory access, no I/O — pure Decimal arithmetic over
already-loaded domain objects, mirroring `RecipeExplosionService`'s own
shape exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.products.entities.recipe_version import RecipeVersion
from backend.domain.products.exceptions import InvalidRecipeError
from backend.domain.products.recipe_enums import OutputType

#: Waste/loss outputs are never something you can "buy back" to reconstruct
#: the base product — only genuine, reusable parts count.
_NON_RECONSTRUCTIVE_OUTPUT_TYPES = frozenset({OutputType.WASTE, OutputType.LOSS})


@dataclass(frozen=True)
class ExplodedComponent:
    component_product_id: str
    quantity: Decimal
    unit_id: str


def _dec(value) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidRecipeError("La cantidad objetivo no puede ser float")
    return Decimal(str(value))


class ReverseRecipeExplosionService:
    def required_components_for(
        self, version: RecipeVersion, target_quantity: Decimal | int | str = Decimal("1"),
    ) -> list[ExplodedComponent]:
        """The parts (and how much of each) needed to reconstruct
        `target_quantity` units of the recipe's base product, per this
        version's declared outputs. Raises if the version has no usable
        (non-waste/loss) outputs at all — there is nothing to reconstruct
        from."""
        factor = _dec(target_quantity)
        if factor <= 0:
            raise InvalidRecipeError("La cantidad objetivo debe ser positiva")
        usable = [o for o in version.outputs if o.output_type not in _NON_RECONSTRUCTIVE_OUTPUT_TYPES]
        if not usable:
            raise InvalidRecipeError(
                "La versión no tiene outputs reconstruibles (todos son merma/pérdida)")
        return [ExplodedComponent(component_product_id=o.product_id,
                                  quantity=o.quantity * factor, unit_id=o.unit_id)
                for o in usable]

    def max_reconstructible_units(
        self, version: RecipeVersion, available_by_product: dict[str, Decimal],
    ) -> Decimal:
        """How many WHOLE units of the base product could be reconstructed
        right now, given `available_by_product` (product_id -> on-hand
        Decimal for each part). The bottleneck part — whichever runs out
        first — caps the result, same as physically assembling units from
        a mixed-quantity parts bin. Zero (never negative, never fabricated)
        when any required part has no stock or the version has nothing
        reconstructible."""
        usable = [o for o in version.outputs if o.output_type not in _NON_RECONSTRUCTIVE_OUTPUT_TYPES]
        if not usable:
            return Decimal("0")
        best = None
        for output in usable:
            if output.quantity <= 0:
                continue
            on_hand = available_by_product.get(output.product_id, Decimal("0"))
            if on_hand <= 0:
                return Decimal("0")
            units_from_this_part = (on_hand // output.quantity)
            if best is None or units_from_this_part < best:
                best = units_from_this_part
        return best if best is not None else Decimal("0")

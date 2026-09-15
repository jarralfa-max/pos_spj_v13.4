"""SellableAvailabilityQueryService — direct + reconstructible availability
(ERP integration master prompt §15-19, Fase 7).

ATP = direct stock + stock reconstructible from a reversible recipe's parts
(§17). Composes two already-canonical reads —
`InventoryAvailabilityQueryService` (direct, per product) and
`RecipeRepository.reversible_active_version_for_product` (is this product's
recipe eligible, and what does it need) — plus the pure
`ReverseRecipeExplosionService` bottleneck calculation. Never writes
anything; the actual reconstruction (reserving parts, consuming them,
producing the base product) is `ReconstructBaseProductUseCase`'s job.

Conservative by design, same discipline as every other cross-context
resolution built this session: any ambiguity (no eligible recipe, more
than one, wrong recipe_type, `reverse_reconstruction_allowed=False`)
resolves to `reconstructible = 0`, never a guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.application.inventory.queries.availability_query_service import (
    InventoryAvailabilityQueryService,
)
from backend.domain.products.exceptions import InvalidRecipeError
from backend.domain.products.services.reverse_recipe_explosion_service import (
    ReverseRecipeExplosionService,
)
from backend.infrastructure.db.repositories.products.recipe_repository import (
    RecipeRepository,
)

_Z = Decimal("0")


@dataclass(frozen=True, slots=True)
class SellableAvailability:
    product_id: str
    branch_id: str
    direct: Decimal = _Z
    reconstructible: Decimal = _Z
    reserved: Decimal = _Z
    available_to_promise: Decimal = _Z
    #: the reversible recipe version that made reconstruction possible, or
    #: None when reconstructible == 0 (nothing eligible, or genuinely 0
    #: reconstructible units from what's on hand).
    recipe_version_id: str | None = None


class SellableAvailabilityQueryService:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._inventory = InventoryAvailabilityQueryService(connection)
        self._recipes = RecipeRepository(connection)
        self._explosion = ReverseRecipeExplosionService()

    def get_sellable_availability(
        self, *, product_id: str, branch_id: str, warehouse_id: str | None = None,
    ) -> SellableAvailability:
        direct_dto = self._inventory.get_availability(
            product_id=product_id, branch_id=branch_id, warehouse_id=warehouse_id)

        reconstructible = _Z
        recipe_version_id = None
        version = self._recipes.reversible_active_version_for_product(product_id)
        if version is not None:
            available_by_part = {
                output.product_id: self._inventory.get_availability(
                    product_id=output.product_id, branch_id=branch_id,
                    warehouse_id=warehouse_id).available
                for output in version.outputs
            }
            try:
                reconstructible = self._explosion.max_reconstructible_units(
                    version, available_by_part)
            except InvalidRecipeError:
                reconstructible = _Z
            if reconstructible > 0:
                recipe_version_id = version.id

        available_to_promise = direct_dto.available + reconstructible
        return SellableAvailability(
            product_id=product_id, branch_id=branch_id,
            direct=direct_dto.available, reconstructible=reconstructible,
            reserved=direct_dto.reserved, available_to_promise=available_to_promise,
            recipe_version_id=recipe_version_id)

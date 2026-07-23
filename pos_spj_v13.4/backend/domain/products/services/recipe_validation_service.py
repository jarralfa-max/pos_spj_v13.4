"""RecipeValidationService — validates a recipe version before approval (§21).

Rules:
- a version must have at least one component or one output;
- multi-output recipe types (disassembly, cutting yield) must declare outputs;
- component product ids must be distinct;
- no circular reference (delegates to the cycle policy);
- output product may not appear as one of its own components (direct cycle).
Pure domain service — no persistence.
"""

from __future__ import annotations

from backend.domain.products.entities.recipe import Recipe
from backend.domain.products.entities.recipe_version import RecipeVersion
from backend.domain.products.exceptions import (
    InvalidRecipeError,
    RecipeCycleDetectedError,
)
from backend.domain.products.recipe_enums import MULTI_OUTPUT_TYPES
from backend.domain.products.services.recipe_cycle_policy import (
    ComponentResolver,
    detect_recipe_cycle,
)


def _no_op_resolver(_product_id: str) -> list[str]:
    return []


class RecipeValidationService:
    def validate(
        self,
        recipe: Recipe,
        version: RecipeVersion,
        *,
        resolver: ComponentResolver | None = None,
    ) -> None:
        if not version.components and not version.outputs:
            raise InvalidRecipeError("La receta requiere componentes u outputs (§21)")

        if recipe.recipe_type in MULTI_OUTPUT_TYPES and not version.outputs:
            raise InvalidRecipeError(
                f"El tipo {recipe.recipe_type.value} requiere outputs declarados")

        component_ids = version.component_product_ids()
        if len(component_ids) != len(set(component_ids)):
            raise InvalidRecipeError("Los componentes no pueden repetirse")

        # ciclo directo: el producto de la receta como su propio componente
        if recipe.product_id in component_ids:
            raise RecipeCycleDetectedError(
                "La receta no puede consumir su propio producto de salida")

        detect_recipe_cycle(
            recipe.product_id, component_ids, resolver or _no_op_resolver)

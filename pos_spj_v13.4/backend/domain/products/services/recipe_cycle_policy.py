"""Recipe cycle policy (§21) — a recipe may not consume its own output.

Detects direct and transitive cycles: producing product A must never require
consuming A, whether A is a direct component or reached through the recipes of its
components. The caller supplies a ``resolver`` mapping a product_id to the list of
component product ids of its active recipe (empty if none). Pure, no persistence.
"""

from __future__ import annotations

from typing import Callable

from backend.domain.products.exceptions import RecipeCycleDetectedError

ComponentResolver = Callable[[str], list[str]]


def detect_recipe_cycle(
    output_product_id: str,
    component_product_ids: list[str],
    resolver: ComponentResolver,
) -> None:
    """Raise if producing ``output_product_id`` would consume itself (§21)."""
    # DFS por el grafo de "para producir X necesito consumir Y".
    stack: list[str] = list(component_product_ids)
    seen: set[str] = set()
    while stack:
        product = stack.pop()
        if product == output_product_id:
            raise RecipeCycleDetectedError(
                f"Ciclo de receta: el producto {output_product_id} se consume a sí mismo")
        if product in seen:
            continue
        seen.add(product)
        stack.extend(resolver(product))

"""Real `RecipeSnapshotPort` backed by Products' canonical recipe/yield/
cutting-scheme catalogs (master-prompt §12/§13: "products debe poseer la
definición de receta/rendimiento; meat_processing debe ejecutar esas
definiciones").

`ports.py`'s `RecipeSnapshotPort` docstring (PROC-6, §40) named this the
deferred integration — "cuando ese bounded context exponga las query
services de §40" — and shipped `NullRecipeSnapshotPort` so
`ReleaseProcessingOrderUseCase` worked standalone until then.
`ProductRecipeQueryService`/`ProductYieldQueryService`/
`ProductCuttingQueryService` now exist and are wired into Products' own UI
(PROD-9/10/11) — this adapter is the missing connection, not a new catalog.

Conservative by design, matching every other port's "never fabricate"
contract in `ports.py`: a catalog contributes to the snapshot only when
`target_product_id` has EXACTLY ONE active row with EXACTLY ONE ACTIVE
version. Zero matches means that catalog legitimately doesn't apply (e.g. a
PACKAGING order with no recipe at all). More than one candidate is a data
state this adapter refuses to guess at — silently picking one would let a
wrong recipe/yield feed the variance calculation `ReleaseProcessingOrderUseCase`
depends on, which corrupts real yield/waste numbers, not just a UI glitch.
In practice this bar is not restrictive: `recipes`/`yield_profiles`/
`cutting_schemes` are meant to be superseded (old version → SUPERSEDED),
never run in parallel, so a real product should never actually trip the
ambiguous case.
"""

from __future__ import annotations

import logging

from backend.application.products.queries.product_cutting_query_service import (
    ProductCuttingQueryService,
)
from backend.application.products.queries.product_recipe_query_service import (
    ProductRecipeQueryService,
)
from backend.application.products.queries.product_yield_query_service import (
    ProductYieldQueryService,
)
from backend.domain.products.recipe_enums import RecipeVersionStatus

from backend.application.meat_processing.ports import RecipeSnapshot

logger = logging.getLogger("spj.meat_processing.products_recipe_snapshot")

_ACTIVE_VERSION_STATUS = RecipeVersionStatus.ACTIVE.value


def _single_active_version(*, catalog_label: str, product_id: str,
                           list_catalog_rows, list_versions, version_detail) -> dict | None:
    """One catalog's `list_X(product_id)` → active row → `ACTIVE` version →
    full `version_detail`. Returns None on zero or ambiguous (>1) matches."""
    active_rows = [row for row in list_catalog_rows(product_id) if row.get("active")]
    candidates: list[dict] = []
    for row in active_rows:
        for version in list_versions(row["id"]):
            if version.get("status") == _ACTIVE_VERSION_STATUS:
                candidates.append(version)
    if not candidates:
        return None
    if len(candidates) > 1:
        logger.warning(
            "%s: %d ACTIVE versions found for product_id=%s (expected at most 1) "
            "— skipping, refusing to guess which applies",
            catalog_label, len(candidates), product_id)
        return None
    return version_detail(candidates[0]["id"])


class ProductsRecipeSnapshotAdapter:
    """Implements `RecipeSnapshotPort` against the real Products catalogs."""

    def __init__(self, connection) -> None:
        self._recipes = ProductRecipeQueryService(connection)
        self._yields = ProductYieldQueryService(connection)
        self._cutting = ProductCuttingQueryService(connection)

    def resolve(self, *, target_product_id: str, process_type) -> RecipeSnapshot | None:
        recipe = _single_active_version(
            catalog_label="recipe", product_id=target_product_id,
            list_catalog_rows=self._recipes.list_recipes,
            list_versions=self._recipes.list_versions,
            version_detail=self._recipes.version_detail)
        yield_profile = _single_active_version(
            catalog_label="yield_profile", product_id=target_product_id,
            list_catalog_rows=self._yields.list_profiles,
            list_versions=self._yields.list_versions,
            version_detail=self._yields.version_detail)
        cutting_scheme = _single_active_version(
            catalog_label="cutting_scheme", product_id=target_product_id,
            list_catalog_rows=self._cutting.list_schemes,
            list_versions=self._cutting.list_versions,
            version_detail=self._cutting.version_detail)

        if recipe is None and yield_profile is None and cutting_scheme is None:
            return None

        outputs: list[dict] = []
        for source in (recipe, yield_profile, cutting_scheme):
            if source is not None:
                outputs.extend(source.get("outputs", []))

        yield_tolerances: dict = {}
        if yield_profile is not None and yield_profile.get("tolerance_pct") is not None:
            yield_tolerances["tolerance_pct"] = yield_profile["tolerance_pct"]

        return RecipeSnapshot(
            recipe_version_id=recipe["id"] if recipe else None,
            cutting_scheme_version_id=cutting_scheme["id"] if cutting_scheme else None,
            yield_profile_version_id=yield_profile["id"] if yield_profile else None,
            components=tuple(recipe.get("components", [])) if recipe else (),
            outputs=tuple(outputs),
            yield_tolerances=yield_tolerances,
        )

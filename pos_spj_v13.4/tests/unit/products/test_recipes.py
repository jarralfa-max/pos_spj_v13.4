"""PROD-9 — recetas versionadas: entidades, validación de ciclos, explosión, versionado."""

from decimal import Decimal

import pytest

from backend.domain.products.entities.recipe import Recipe
from backend.domain.products.entities.recipe_component import RecipeComponent
from backend.domain.products.entities.recipe_output import RecipeOutput
from backend.domain.products.entities.recipe_version import RecipeVersion
from backend.domain.products.exceptions import (
    InvalidRecipeError,
    RecipeCycleDetectedError,
    RecipeVersionImmutableError,
    RecipeYieldInvalidError,
)
from backend.domain.products.recipe_enums import (
    OutputType,
    RecipeType,
    RecipeVersionStatus,
)
from backend.domain.products.services.recipe_cycle_policy import detect_recipe_cycle
from backend.domain.products.services.recipe_explosion_service import (
    RecipeExplosionService,
)
from backend.domain.products.services.recipe_validation_service import (
    RecipeValidationService,
)


def _comp(pid="c1", qty="2", scrap="0"):
    return RecipeComponent(component_product_id=pid, quantity=Decimal(qty),
                           unit_id="kg", scrap_pct=Decimal(scrap))


# ── componentes / outputs ────────────────────────────────────────────────────
class TestLines:
    def test_component_float_rejected(self):
        with pytest.raises(InvalidRecipeError):
            RecipeComponent(component_product_id="c1", quantity=2.0, unit_id="kg")

    def test_component_positive_qty(self):
        with pytest.raises(InvalidRecipeError):
            RecipeComponent(component_product_id="c1", quantity=Decimal("0"), unit_id="kg")

    def test_gross_quantity_with_scrap(self):
        c = _comp(qty="9", scrap="10")   # 9 / 0.9 = 10
        assert c.gross_quantity() == Decimal("10")

    def test_output_yield_bounds(self):
        with pytest.raises(RecipeYieldInvalidError):
            RecipeOutput(product_id="p1", output_type=OutputType.MAIN_PRODUCT,
                         quantity=Decimal("1"), unit_id="kg",
                         expected_yield_pct=Decimal("120"))

    def test_output_type_coercion(self):
        o = RecipeOutput(product_id="p1", output_type="CO_PRODUCT",
                         quantity=Decimal("1"), unit_id="kg")
        assert o.output_type is OutputType.CO_PRODUCT


# ── versionado (§22) ─────────────────────────────────────────────────────────
class TestVersioning:
    def _draft(self):
        v = RecipeVersion(recipe_id="r1", version_number=1)
        v.add_component(_comp())
        return v

    def test_lifecycle_draft_to_active(self):
        v = self._draft()
        v.submit(); v.approve(approved_by_user_id="mgr"); v.activate()
        assert v.status is RecipeVersionStatus.ACTIVE and v.effective_from

    def test_active_version_immutable(self):
        v = self._draft()
        v.submit(); v.approve(approved_by_user_id="mgr"); v.activate()
        with pytest.raises(RecipeVersionImmutableError):
            v.add_component(_comp(pid="c2"))

    def test_approved_version_immutable(self):
        v = self._draft()
        v.submit(); v.approve(approved_by_user_id="mgr")
        with pytest.raises(RecipeVersionImmutableError):
            v.add_output(RecipeOutput(product_id="p1", output_type=OutputType.MAIN_PRODUCT,
                                      quantity=Decimal("1"), unit_id="kg"))

    def test_cannot_submit_empty(self):
        v = RecipeVersion(recipe_id="r1", version_number=1)
        with pytest.raises(InvalidRecipeError):
            v.submit()

    def test_illegal_transition(self):
        v = self._draft()
        with pytest.raises(InvalidRecipeError):
            v.activate()  # DRAFT → ACTIVE no permitido

    def test_supersede_sets_effective_to(self):
        v = self._draft()
        v.submit(); v.approve(approved_by_user_id="mgr"); v.activate(); v.supersede()
        assert v.status is RecipeVersionStatus.SUPERSEDED and v.effective_to


# ── cycle policy (§21) ───────────────────────────────────────────────────────
class TestCycle:
    def test_direct_cycle(self):
        with pytest.raises(RecipeCycleDetectedError):
            detect_recipe_cycle("A", ["A"], lambda _p: [])

    def test_transitive_cycle(self):
        # A consume B; B consume A  → ciclo
        graph = {"B": ["A"]}
        with pytest.raises(RecipeCycleDetectedError):
            detect_recipe_cycle("A", ["B"], lambda p: graph.get(p, []))

    def test_no_cycle(self):
        graph = {"B": ["C"], "C": []}
        detect_recipe_cycle("A", ["B"], lambda p: graph.get(p, []))


# ── validation service ───────────────────────────────────────────────────────
class TestValidation:
    def _recipe(self, rtype=RecipeType.PRODUCTION_BOM):
        return Recipe(product_id="P", recipe_type=rtype, name="R")

    def test_valid_bom(self):
        v = RecipeVersion(recipe_id="r1", version_number=1)
        v.add_component(_comp("c1")); v.add_component(_comp("c2"))
        RecipeValidationService().validate(self._recipe(), v)

    def test_self_consuming_rejected(self):
        v = RecipeVersion(recipe_id="r1", version_number=1)
        v.add_component(_comp("P"))   # product P consume P
        with pytest.raises(RecipeCycleDetectedError):
            RecipeValidationService().validate(self._recipe(), v)

    def test_duplicate_components_rejected(self):
        v = RecipeVersion(recipe_id="r1", version_number=1)
        v.add_component(_comp("c1")); v.add_component(_comp("c1"))
        with pytest.raises(InvalidRecipeError):
            RecipeValidationService().validate(self._recipe(), v)

    def test_disassembly_requires_outputs(self):
        v = RecipeVersion(recipe_id="r1", version_number=1)
        v.add_component(_comp("canal"))
        with pytest.raises(InvalidRecipeError):
            RecipeValidationService().validate(self._recipe(RecipeType.DISASSEMBLY), v)


# ── explosion service (§27) ──────────────────────────────────────────────────
class TestExplosion:
    def test_explode_scales_quantities(self):
        v = RecipeVersion(recipe_id="r1", version_number=1)
        v.add_component(_comp("c1", qty="2"))
        v.add_component(_comp("c2", qty="3"))
        result = RecipeExplosionService().explode(v, Decimal("5"), include_scrap=False)
        qty = {e.component_product_id: e.quantity for e in result}
        assert qty["c1"] == Decimal("10") and qty["c2"] == Decimal("15")

    def test_explode_includes_scrap(self):
        v = RecipeVersion(recipe_id="r1", version_number=1)
        v.add_component(_comp("c1", qty="9", scrap="10"))  # gross 10
        result = RecipeExplosionService().explode(v, Decimal("1"))
        assert result[0].quantity == Decimal("10")

    def test_explode_rejects_non_positive_target(self):
        v = RecipeVersion(recipe_id="r1", version_number=1)
        v.add_component(_comp("c1"))
        with pytest.raises(InvalidRecipeError):
            RecipeExplosionService().explode(v, Decimal("0"))

"""Fase 7 (§15-19) — ReverseRecipeExplosionService: the pure bottleneck
calculation behind reconstructing a base product from its disassembled
parts (whole chicken <- breast/leg/wing on hand)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.products.entities.recipe_output import RecipeOutput
from backend.domain.products.entities.recipe_version import RecipeVersion
from backend.domain.products.exceptions import InvalidRecipeError
from backend.domain.products.recipe_enums import OutputType, RecipeVersionStatus
from backend.domain.products.services.reverse_recipe_explosion_service import (
    ExplodedComponent,
    ReverseRecipeExplosionService,
)

_UNIT = "unit-kg"


def _version(outputs):
    return RecipeVersion(recipe_id="r1", version_number=1,
                         status=RecipeVersionStatus.ACTIVE, outputs=outputs)


def _chicken_outputs():
    return [
        RecipeOutput(product_id="breast", output_type=OutputType.MAIN_PRODUCT,
                    quantity=Decimal("1.2"), unit_id=_UNIT),
        RecipeOutput(product_id="leg", output_type=OutputType.CO_PRODUCT,
                    quantity=Decimal("0.8"), unit_id=_UNIT),
        RecipeOutput(product_id="wing", output_type=OutputType.CO_PRODUCT,
                    quantity=Decimal("0.4"), unit_id=_UNIT),
        RecipeOutput(product_id="feathers", output_type=OutputType.WASTE,
                    quantity=Decimal("0.2"), unit_id=_UNIT),
    ]


class TestRequiredComponentsFor:
    def test_excludes_waste_and_scales_by_target_quantity(self):
        version = _version(_chicken_outputs())
        service = ReverseRecipeExplosionService()

        result = service.required_components_for(version, target_quantity=Decimal("3"))

        assert set(c.component_product_id for c in result) == {"breast", "leg", "wing"}
        by_product = {c.component_product_id: c.quantity for c in result}
        assert by_product["breast"] == Decimal("3.6")
        assert by_product["leg"] == Decimal("2.4")
        assert by_product["wing"] == Decimal("1.2")

    def test_rejects_non_positive_target_quantity(self):
        version = _version(_chicken_outputs())
        service = ReverseRecipeExplosionService()

        with pytest.raises(InvalidRecipeError):
            service.required_components_for(version, target_quantity=Decimal("0"))

    def test_rejects_when_only_waste_outputs_exist(self):
        version = _version([RecipeOutput(product_id="feathers", output_type=OutputType.WASTE,
                                         quantity=Decimal("1"), unit_id=_UNIT)])
        service = ReverseRecipeExplosionService()

        with pytest.raises(InvalidRecipeError):
            service.required_components_for(version)


class TestMaxReconstructibleUnits:
    def test_bottleneck_component_caps_the_result(self):
        version = _version(_chicken_outputs())
        service = ReverseRecipeExplosionService()
        # breast: 12kg/1.2 = 10 chickens' worth; leg: 8/0.8 = 10; wing: 1.2/0.4 = 3 <- bottleneck
        available = {"breast": Decimal("12"), "leg": Decimal("8"), "wing": Decimal("1.2")}

        assert service.max_reconstructible_units(version, available) == Decimal("3")

    def test_floors_to_whole_units(self):
        version = _version(_chicken_outputs())
        service = ReverseRecipeExplosionService()
        # wing: 1.5 / 0.4 = 3.75 -> floors to 3; others abundant
        available = {"breast": Decimal("100"), "leg": Decimal("100"), "wing": Decimal("1.5")}

        assert service.max_reconstructible_units(version, available) == Decimal("3")

    def test_missing_part_yields_zero_not_a_guess(self):
        version = _version(_chicken_outputs())
        service = ReverseRecipeExplosionService()
        available = {"breast": Decimal("12"), "leg": Decimal("8")}  # no wing at all

        assert service.max_reconstructible_units(version, available) == Decimal("0")

    def test_no_usable_outputs_yields_zero(self):
        version = _version([RecipeOutput(product_id="feathers", output_type=OutputType.WASTE,
                                         quantity=Decimal("1"), unit_id=_UNIT)])
        service = ReverseRecipeExplosionService()

        assert service.max_reconstructible_units(version, {"feathers": Decimal("999")}) == Decimal("0")

    def test_zero_stock_of_every_part_yields_zero(self):
        version = _version(_chicken_outputs())
        service = ReverseRecipeExplosionService()

        assert service.max_reconstructible_units(version, {}) == Decimal("0")

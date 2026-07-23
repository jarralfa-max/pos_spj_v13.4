"""PROD-6 — productos internos / WIP / semi-terminados: roles, visibilidad, policy."""

import pytest

from backend.domain.products.entities.product import Product
from backend.domain.products.enums import ProductRole, ProductType
from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.internal_enums import INTERNAL_STAGES, InternalStage
from backend.domain.products.policies.internal_product_policy import (
    is_transformation,
    validate_internal_product,
)


def _product(**kw):
    base = dict(code="WIP-001", name="Carne deshuesada",
                product_type=ProductType.SEMI_FINISHED_GOOD, base_unit_id="kg",
                category_id="cat-1")
    base.update(kw)
    return Product(**base)


class TestInternalStageFlag:
    def test_wip_forces_internal_only(self):
        p = _product(internal_stage=InternalStage.WORK_IN_PROGRESS)
        assert p.internal_only is True
        assert p.is_internal and p.is_work_in_progress

    def test_stage_string_coerced(self):
        p = _product(internal_stage="SEMI_FINISHED")
        assert p.internal_stage is InternalStage.SEMI_FINISHED

    def test_default_stage_is_none(self):
        assert _product().internal_stage is InternalStage.NONE

    def test_internal_stage_and_sellable_conflict(self):
        with pytest.raises(ProductsDomainError):
            _product(internal_stage=InternalStage.WORK_IN_PROGRESS, sellable=True)


class TestVisibility:
    def test_internal_not_visible_in_pos(self):
        p = _product(internal_stage=InternalStage.PROCESS_INTERMEDIATE)
        assert not p.is_visible_in_pos()

    def test_normal_sellable_is_visible(self):
        p = Product(code="ABR", name="Refresco", product_type=ProductType.RESALE_PRODUCT,
                    base_unit_id="pza", category_id="c1", sellable=True)
        assert p.is_visible_in_pos()

    def test_internal_not_sellable_now_even_if_active(self):
        p = _product(internal_stage=InternalStage.WORK_IN_PROGRESS)
        p.activate()
        assert not p.is_sellable_now()


class TestRolesAndRecipeUse:
    def test_internal_role_present(self):
        p = _product(internal_stage=InternalStage.SEMI_FINISHED, inventory_managed=True)
        assert ProductRole.INTERNAL_ONLY in p.roles
        assert ProductRole.INVENTORY_MANAGED in p.roles

    def test_internal_can_be_recipe_component(self):
        p = _product(internal_stage=InternalStage.WORK_IN_PROGRESS)
        assert p.can_be_recipe_component()

    def test_producible_can_be_recipe_component(self):
        p = Product(code="SALSA-1", name="Salsa", product_type=ProductType.FINISHED_GOOD,
                    base_unit_id="l", category_id="c1", producible=True)
        assert p.can_be_recipe_component()

    def test_internal_can_have_inventory_and_cost(self):
        p = _product(internal_stage=InternalStage.SEMI_FINISHED,
                     inventory_managed=True, quality_controlled=True, lot_controlled=True)
        # puede existir en inventario, con calidad y lote (§13)
        assert p.inventory_managed and p.quality_controlled and p.lot_controlled


class TestInternalPolicy:
    def test_validate_internal_ok(self):
        validate_internal_product(_product(internal_stage=InternalStage.WORK_IN_PROGRESS))

    def test_validate_non_internal_noop(self):
        validate_internal_product(Product(
            code="ABR", name="Refresco", product_type=ProductType.RESALE_PRODUCT,
            base_unit_id="pza", category_id="c1", sellable=True))

    def test_transformation_between_stages(self):
        assert is_transformation(InternalStage.WORK_IN_PROGRESS, InternalStage.SEMI_FINISHED)
        assert not is_transformation(InternalStage.SEMI_FINISHED, InternalStage.SEMI_FINISHED)
        assert not is_transformation(InternalStage.NONE, InternalStage.NONE)

    def test_internal_stages_set(self):
        assert InternalStage.WORK_IN_PROGRESS in INTERNAL_STAGES
        assert InternalStage.NONE not in INTERNAL_STAGES

"""Products→Meat Processing recipe snapshot integration (§12/§13 of the ERP
integration master prompt): `ReleaseProcessingOrderUseCase` used to always
resolve `None` in production — `meat_processing_factory.py` never passed a
`recipe_snapshot_port`, defaulting to `NullRecipeSnapshotPort`, so no order
ever captured a real recipe/yield/cutting-scheme version, no matter what was
active in Products. `ProductsRecipeSnapshotAdapter` is the real
implementation; this proves it resolves a genuinely activated recipe and
that `ReleaseProcessingOrderUseCase` threads it through end-to-end.
"""

from __future__ import annotations

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.integrations.products_recipe_snapshot_adapter import (
    ProductsRecipeSnapshotAdapter,
)
from backend.application.meat_processing.use_cases import (
    ApproveProcessingOrderUseCase,
    CreateProcessingOrderUseCase,
    ReleaseProcessingOrderUseCase,
)
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_recipe_commands import (
    CreateRecipeCommand,
    RecipeVersionTransitionCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.use_cases.product_recipe_use_cases import (
    ActivateRecipeVersionUseCase,
    ApproveRecipeVersionUseCase,
    CreateProductRecipeUseCase,
    SubmitRecipeVersionUseCase,
)
from backend.domain.meat_processing.enums import ProcessType
from backend.infrastructure.db.repositories.meat_processing.unit_of_work import (
    MeatProcessingUnitOfWork,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.shared.ids import new_uuid


class _AllowAllChecker:
    def has_permission(self, user_id, code):
        return True


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    importlib.import_module(
        "migrations.standalone.187_meat_processing_bounded_context_schema"
    ).run(c)
    yield c
    c.close()


def _activate_recipe(conn, *, product_id, recipe_type="PRODUCTION_BOM",
                     component_id=None, output_id=None, creator="alice",
                     approver="bob") -> str:
    """Create → submit → approve → activate a real recipe version, exactly
    like a Products user would through the UI. Returns the version_id.

    `CUTTING_YIELD`/`DISASSEMBLY` are 1-input→N-outputs types and require
    `outputs`, not `components` (`Recipe`'s own validation rejects the
    reverse) — pass `output_id` for those, leave it out for a plain
    components-consuming type like the default `PRODUCTION_BOM`.
    """
    auth = ProductsAuthorizationPolicy(_AllowAllChecker())
    kwargs = dict(
        operation_id=new_uuid(), product_id=product_id, recipe_type=recipe_type,
        name="Receta de prueba", user_id=creator)
    if output_id is not None:
        kwargs["outputs"] = [{"product_id": output_id, "output_type": "MAIN_PRODUCT",
                              "quantity": "1", "unit_id": new_uuid(),
                              "expected_yield_pct": "50"}]
    else:
        kwargs["components"] = [{"component_product_id": component_id or new_uuid(),
                                 "quantity": "1", "unit_id": new_uuid()}]
    created = CreateProductRecipeUseCase(conn, auth).execute(CreateRecipeCommand(**kwargs))
    assert created.success, created.message
    version_id = created.version_id

    def _transition(use_case_cls, user_id):
        result = use_case_cls(conn, auth).execute(RecipeVersionTransitionCommand(
            operation_id=new_uuid(), version_id=version_id, user_id=user_id))
        assert result.success, result.message

    _transition(SubmitRecipeVersionUseCase, creator)
    _transition(ApproveRecipeVersionUseCase, approver)
    _transition(ActivateRecipeVersionUseCase, approver)
    return version_id


class TestAdapterResolvesARealActiveRecipe:
    def test_resolves_the_active_version_with_its_components(self, conn):
        product_id = new_uuid()
        version_id = _activate_recipe(conn, product_id=product_id)

        snapshot = ProductsRecipeSnapshotAdapter(conn).resolve(
            target_product_id=product_id, process_type=ProcessType.CUTTING)

        assert snapshot is not None
        assert snapshot.recipe_version_id == version_id
        assert len(snapshot.components) == 1
        assert snapshot.cutting_scheme_version_id is None
        assert snapshot.yield_profile_version_id is None

    def test_no_active_recipe_resolves_to_none(self, conn):
        snapshot = ProductsRecipeSnapshotAdapter(conn).resolve(
            target_product_id=new_uuid(), process_type=ProcessType.PACKAGING)

        assert snapshot is None

    def test_a_draft_recipe_is_not_resolved(self, conn):
        auth = ProductsAuthorizationPolicy(_AllowAllChecker())
        product_id = new_uuid()
        created = CreateProductRecipeUseCase(conn, auth).execute(CreateRecipeCommand(
            operation_id=new_uuid(), product_id=product_id, recipe_type="FORMULA",
            name="Sin activar", user_id="alice",
            components=[{"component_product_id": new_uuid(), "quantity": "1",
                        "unit_id": new_uuid()}]))
        assert created.success

        snapshot = ProductsRecipeSnapshotAdapter(conn).resolve(
            target_product_id=product_id, process_type=ProcessType.MIXING)

        assert snapshot is None

    def test_two_active_recipes_for_the_same_product_are_refused_not_guessed(self, conn):
        """A genuinely ambiguous data state (should not occur if activation
        supersedes correctly, but the adapter must not gamble on it)."""
        product_id = new_uuid()
        _activate_recipe(conn, product_id=product_id, recipe_type="PRODUCTION_BOM")
        # Bypass the domain's own supersede-on-activate rule by activating a
        # second, independent recipe (different id) for the same product —
        # exactly the "more than one ACTIVE version" case the adapter guards.
        _activate_recipe(conn, product_id=product_id, recipe_type="FORMULA",
                         creator="carol", approver="dave")

        snapshot = ProductsRecipeSnapshotAdapter(conn).resolve(
            target_product_id=product_id, process_type=ProcessType.CUTTING)

        assert snapshot is None


class TestReleaseProcessingOrderCapturesTheRealSnapshot:
    def test_release_captures_the_active_recipe_version(self, conn):
        product_id = new_uuid()
        version_id = _activate_recipe(conn, product_id=product_id)

        order = CreateProcessingOrderUseCase().execute(
            conn, operation_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
            process_type=ProcessType.CUTTING, target_product_id=product_id,
            planned_quantity=Decimal("10"), planned_weight=Decimal("100"),
            actor_user_id=new_uuid())
        assert order.success
        ApproveProcessingOrderUseCase().execute(
            conn, order_id=order.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())

        release = ReleaseProcessingOrderUseCase(
            recipe_snapshot_port=ProductsRecipeSnapshotAdapter(conn)).execute(
            conn, order_id=order.entity_id, operation_id=new_uuid(),
            actor_user_id=new_uuid())

        assert release.success, release.message
        with MeatProcessingUnitOfWork(conn) as uow:
            persisted = uow.orders.get(order.entity_id)
        assert persisted.recipe_version_id == version_id

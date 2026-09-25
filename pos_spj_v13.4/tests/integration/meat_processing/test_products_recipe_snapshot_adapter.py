"""Products → Procesamiento: `ProductsRecipeSnapshotAdapter` resuelve la
definición productiva SEGÚN LA FAMILIA del proceso, desde versiones realmente
activadas en Productos:

- FORMULACIÓN: la receta de producción del producto a fabricar (componentes).
- DESPIECE: el esquema de corte de la entrada — nunca una receta de producción.

Ambigüedad (dos versiones activas) o borradores no se adivinan: no hay
definición. Que la orden congele esta definición al PREPARAR se prueba en
`test_released_order_executes_frozen_snapshot.py`.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

from backend.application.meat_processing.integrations.products_recipe_snapshot_adapter import (
    ProductsRecipeSnapshotAdapter,
)
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_recipe_commands import (
    CreateRecipeCommand,
    RecipeVersionTransitionCommand,
)
from backend.application.products.use_cases.product_recipe_use_cases import (
    ActivateRecipeVersionUseCase,
    ApproveRecipeVersionUseCase,
    CreateProductRecipeUseCase,
    SubmitRecipeVersionUseCase,
)
from backend.domain.meat_processing.entities.processing_recipe_snapshot import InputRole
from backend.domain.meat_processing.enums import ProcessType
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


class TestFormulationResolvesTheActiveRecipeOfTheProducedProduct:
    def test_components_become_inputs_and_the_product_is_the_output(self, conn):
        product_id, component_id = new_uuid(), new_uuid()
        version_id = _activate_recipe(conn, product_id=product_id, component_id=component_id)

        snapshot = ProductsRecipeSnapshotAdapter(conn).resolve(
            target_product_id=product_id, process_type=ProcessType.MIXING)

        assert snapshot is not None
        assert snapshot.recipe_version_id == version_id
        assert [(i.product_id, i.role) for i in snapshot.inputs] == [
            (component_id, InputRole.COMPONENT)]
        assert [o.product_id for o in snapshot.outputs] == [product_id]
        assert snapshot.cutting_scheme_version_id is None

    def test_no_active_recipe_resolves_to_none(self, conn):
        snapshot = ProductsRecipeSnapshotAdapter(conn).resolve(
            target_product_id=new_uuid(), process_type=ProcessType.MIXING)

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
        """Un estado ambiguo (no debería ocurrir si activar sustituye bien) no se
        adivina: no hay definición y la preparación lo dirá."""
        product_id = new_uuid()
        _activate_recipe(conn, product_id=product_id, recipe_type="PRODUCTION_BOM")
        _activate_recipe(conn, product_id=product_id, recipe_type="FORMULA",
                         creator="carol", approver="dave")

        snapshot = ProductsRecipeSnapshotAdapter(conn).resolve(
            target_product_id=product_id, process_type=ProcessType.FORMULATION)

        assert snapshot is None


class TestDisassemblyNeverUsesAProductionRecipe:
    def test_a_cutting_with_only_a_production_recipe_has_no_definition(self, conn):
        """Antes un corte se 'resolvía' con la receta de producción del producto
        y se liberaba sin esquema de corte. El despiece se define por el ESQUEMA
        DE CORTE de su entrada."""
        product_id = new_uuid()
        _activate_recipe(conn, product_id=product_id)

        snapshot = ProductsRecipeSnapshotAdapter(conn).resolve(
            target_product_id=product_id, process_type=ProcessType.CUTTING)

        assert snapshot is None

"""Recetas — capa de aplicación: crear/editar/enviar/aprobar/activar + segregación."""

import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_recipe_commands import (
    CreateRecipeCommand,
    RecipeVersionTransitionCommand,
    UpdateDraftVersionCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.queries.product_recipe_query_service import (
    ProductRecipeQueryService,
)
from backend.application.products.use_cases.product_recipe_use_cases import (
    ActivateRecipeVersionUseCase,
    ApproveRecipeVersionUseCase,
    CreateProductRecipeUseCase,
    SubmitRecipeVersionUseCase,
    UpdateDraftVersionUseCase,
)
from backend.domain.products.exceptions import (
    ProductPermissionDeniedError,
    SegregationOfDutiesError,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema

_PROD = "prod-virtual"
_COMP = "prod-comp"
_UNIT = "unit-kg"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    yield c
    c.close()


class _Checker:
    def __init__(self, granted):
        self._granted = set(granted)

    def has_permission(self, user_id, code):
        return code in self._granted


_P = ProductPermissions
_ALL = ProductsAuthorizationPolicy(_Checker({
    _P.RECIPE_CREATE, _P.RECIPE_EDIT, _P.RECIPE_APPROVE, _P.RECIPE_ACTIVATE}))

_COMPONENTS = [{"component_product_id": _COMP, "quantity": "2", "unit_id": _UNIT}]


def _create(conn, auth=None, creator="creator", components=None):
    return CreateProductRecipeUseCase(conn, auth or _ALL).execute(CreateRecipeCommand(
        operation_id="op", product_id=_PROD, recipe_type="PRODUCTION_BOM",
        name="BOM Playera", components=components or _COMPONENTS, user_id=creator))


def test_create_recipe_with_draft_version(conn):
    r = _create(conn)
    assert r.success and r.recipe_id and r.version_id
    v = conn.execute("SELECT status, version_number, created_by FROM recipe_versions "
                     "WHERE id=?", (r.version_id,)).fetchone()
    assert v["status"] == "DRAFT" and v["version_number"] == 1
    assert v["created_by"] == "creator"
    comp = conn.execute("SELECT quantity FROM recipe_components WHERE version_id=?",
                        (r.version_id,)).fetchone()
    assert comp["quantity"] == "2"


def test_create_requires_permission(conn):
    auth = ProductsAuthorizationPolicy(_Checker(set()))
    with pytest.raises(ProductPermissionDeniedError):
        _create(conn, auth=auth)


def test_create_rejects_self_component(conn):
    # ciclo directo: el producto no puede ser su propio componente.
    r = _create(conn, components=[{"component_product_id": _PROD, "quantity": "1",
                                   "unit_id": _UNIT}])
    assert not r.success and "propio" in r.message.lower()


def test_create_emits_event(conn):
    r = _create(conn)
    row = conn.execute("SELECT event_name FROM product_outbox WHERE entity_id=?",
                       (r.recipe_id,)).fetchone()
    assert row["event_name"] == "PRODUCT_RECIPE_CREATED"


def test_update_draft_replaces_lines(conn):
    r = _create(conn)
    u = UpdateDraftVersionUseCase(conn, _ALL).execute(UpdateDraftVersionCommand(
        operation_id="op2", version_id=r.version_id,
        components=[{"component_product_id": _COMP, "quantity": "5", "unit_id": _UNIT}],
        user_id="creator"))
    assert u.success
    comp = conn.execute("SELECT quantity FROM recipe_components WHERE version_id=?",
                        (r.version_id,)).fetchone()
    assert comp["quantity"] == "5"


def test_full_lifecycle_submit_approve_activate(conn):
    r = _create(conn, creator="alice")
    assert SubmitRecipeVersionUseCase(conn, _ALL).execute(
        RecipeVersionTransitionCommand(operation_id="s", version_id=r.version_id,
                                       user_id="alice")).success
    # Aprobar/activar por un segundo usuario (segregación).
    assert ApproveRecipeVersionUseCase(conn, _ALL).execute(
        RecipeVersionTransitionCommand(operation_id="a", version_id=r.version_id,
                                       user_id="bob")).success
    assert ActivateRecipeVersionUseCase(conn, _ALL).execute(
        RecipeVersionTransitionCommand(operation_id="ac", version_id=r.version_id,
                                       user_id="bob")).success
    assert conn.execute("SELECT status FROM recipe_versions WHERE id=?",
                        (r.version_id,)).fetchone()["status"] == "ACTIVE"


def test_creator_cannot_approve(conn):
    r = _create(conn, creator="alice")
    SubmitRecipeVersionUseCase(conn, _ALL).execute(RecipeVersionTransitionCommand(
        operation_id="s", version_id=r.version_id, user_id="alice"))
    with pytest.raises(SegregationOfDutiesError):
        ApproveRecipeVersionUseCase(conn, _ALL).execute(RecipeVersionTransitionCommand(
            operation_id="a", version_id=r.version_id, user_id="alice"))


def test_activate_supersedes_previous_active(conn):
    # v1 activada, luego v2 activada → v1 pasa a SUPERSEDED.
    r1 = _create(conn, creator="alice")
    for uc, u in ((SubmitRecipeVersionUseCase, "alice"),
                  (ApproveRecipeVersionUseCase, "bob"),
                  (ActivateRecipeVersionUseCase, "bob")):
        uc(conn, _ALL).execute(RecipeVersionTransitionCommand(
            operation_id=f"t{u}1", version_id=r1.version_id, user_id=u))
    # Nueva versión de la MISMA receta (v2) a mano vía repo para la prueba.
    from backend.domain.products.entities.recipe_version import RecipeVersion
    from backend.domain.products.entities.recipe_component import RecipeComponent
    from backend.infrastructure.db.repositories.products.recipe_repository import (
        RecipeRepository,
    )
    repo = RecipeRepository(conn)
    v2 = RecipeVersion(recipe_id=r1.recipe_id, version_number=2, created_by="alice",
                       components=[RecipeComponent(component_product_id=_COMP,
                                                   quantity="3", unit_id=_UNIT)])
    repo.save_version(v2)
    conn.commit()
    for uc, u in ((SubmitRecipeVersionUseCase, "alice"),
                  (ApproveRecipeVersionUseCase, "bob"),
                  (ActivateRecipeVersionUseCase, "bob")):
        assert uc(conn, _ALL).execute(RecipeVersionTransitionCommand(
            operation_id=f"t{u}2", version_id=v2.id, user_id=u)).success
    statuses = {row["version_number"]: row["status"] for row in conn.execute(
        "SELECT version_number, status FROM recipe_versions WHERE recipe_id=?",
        (r1.recipe_id,)).fetchall()}
    assert statuses == {1: "SUPERSEDED", 2: "ACTIVE"}


# ── query service ────────────────────────────────────────────────────────────
def test_query_lists_recipes_and_detail(conn):
    r = _create(conn)
    q = ProductRecipeQueryService(conn)
    recipes = q.list_recipes(_PROD)
    assert recipes[0]["name"] == "BOM Playera"
    versions = q.list_versions(r.recipe_id)
    assert versions[0]["version_number"] == 1
    detail = q.version_detail(r.version_id)
    assert detail["components"][0]["component_product_id"] == _COMP

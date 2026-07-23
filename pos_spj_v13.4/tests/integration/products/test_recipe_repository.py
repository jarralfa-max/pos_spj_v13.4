"""PROD-9 — persistencia de recetas versionadas + resolver de ciclos por versión ACTIVA."""

import sqlite3
from decimal import Decimal

import pytest

from backend.domain.products.entities.recipe import Recipe
from backend.domain.products.entities.recipe_component import RecipeComponent
from backend.domain.products.entities.recipe_output import RecipeOutput
from backend.domain.products.entities.recipe_version import RecipeVersion
from backend.domain.products.recipe_enums import OutputType, RecipeType
from backend.infrastructure.db.repositories.products.recipe_repository import (
    RecipeRepository,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema


@pytest.fixture
def repo():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    for pid in ("P", "c1", "c2"):
        c.execute("INSERT INTO products (id,code,name,name_normalized,product_type,"
                  "lifecycle_status,base_unit_id) VALUES (?,?,?,?,?,?,?)",
                  (pid, pid.upper(), pid, pid, "FINISHED_GOOD", "ACTIVE", "kg"))
    c.commit()
    yield RecipeRepository(c)
    c.close()


def _active_version(repo, recipe_id="r1", product="P"):
    r = Recipe(id=recipe_id, product_id=product, recipe_type=RecipeType.PRODUCTION_BOM,
               name="Salsa")
    repo.save_recipe(r)
    v = RecipeVersion(recipe_id=r.id, version_number=1)
    v.add_component(RecipeComponent(component_product_id="c1", quantity=Decimal("2"),
                                    unit_id="kg", scrap_pct=Decimal("5")))
    v.add_output(RecipeOutput(product_id=product, output_type=OutputType.MAIN_PRODUCT,
                              quantity=Decimal("1"), unit_id="kg",
                              expected_yield_pct=Decimal("95")))
    v.submit(); v.approve(approved_by_user_id="mgr"); v.activate()
    repo.save_version(v)
    return r, v


def test_version_round_trip(repo):
    _r, v = _active_version(repo)
    got = repo.get_version(v.id)
    assert got.status.value == "ACTIVE"
    assert len(got.components) == 1 and got.components[0].scrap_pct == Decimal("5")
    assert got.outputs[0].expected_yield_pct == Decimal("95")


def test_active_version_for_product(repo):
    _active_version(repo)
    got = repo.active_version_for_product("P")
    assert got is not None and got.component_product_ids() == ["c1"]


def test_component_resolver_reflects_active(repo):
    _active_version(repo)
    resolve = repo.component_resolver()
    assert resolve("P") == ["c1"]
    assert resolve("c1") == []   # sin receta activa


def test_save_replaces_lines(repo):
    _r, v = _active_version(repo)
    # nueva versión editable con distinta composición
    v2 = RecipeVersion(recipe_id=v.recipe_id, version_number=2)
    v2.add_component(RecipeComponent(component_product_id="c2", quantity=Decimal("4"),
                                     unit_id="kg"))
    repo.save_version(v2)
    got = repo.get_version(v2.id)
    assert got.component_product_ids() == ["c2"]

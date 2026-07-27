"""Recetas UI — flujo presenter/diálogos: crear receta y listar versiones."""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.catalog_read_service import (  # noqa: E402
    ProductCatalogReadService,
)
from backend.application.products.queries.product_recipe_query_service import (  # noqa: E402
    ProductRecipeQueryService,
)
from backend.application.products.use_cases.product_recipe_use_cases import (  # noqa: E402
    ActivateRecipeVersionUseCase,
    ApproveRecipeVersionUseCase,
    CreateProductRecipeUseCase,
    SubmitRecipeVersionUseCase,
    UpdateDraftVersionUseCase,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from frontend.desktop.modules.products.presenter import ProductsPresenter  # noqa: E402

_PROD = "prod-1"


class _Session:
    user_id = "u1"


@pytest.fixture
def presenter():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_products_schema(conn)
    conn.commit()

    p = ProductsPresenter(
        read_service_factory=lambda: ProductCatalogReadService(conn),
        recipes_read_factory=lambda: ProductRecipeQueryService(conn),
        recipes_write_factory=lambda: {
            "create": CreateProductRecipeUseCase(conn),
            "update": UpdateDraftVersionUseCase(conn),
            "submit": SubmitRecipeVersionUseCase(conn),
            "approve": ApproveRecipeVersionUseCase(conn),
            "activate": ActivateRecipeVersionUseCase(conn),
        },
        session_context=_Session())
    p._conn = conn
    yield p
    conn.close()


def test_presenter_can_manage_recipes(presenter):
    assert presenter.can_manage_recipes is True


def test_create_and_list_recipe(presenter):
    ok, _msg = presenter.create_recipe(
        product_id=_PROD, recipe_type="PRODUCTION_BOM", name="BOM",
        components=[{"component_product_id": "c1", "quantity": "2", "unit_id": "u"}])
    assert ok
    recipes = presenter.list_recipes(_PROD)
    assert recipes[0]["name"] == "BOM"
    versions = presenter.list_recipe_versions(recipes[0]["id"])
    assert versions[0]["status"] == "DRAFT"


def test_dialog_lists_recipes(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.recipes_dialog import RecipesDialog
    presenter.create_recipe(
        product_id=_PROD, recipe_type="PRODUCTION_BOM", name="BOM",
        components=[{"component_product_id": "c1", "quantity": "2", "unit_id": "u"}])
    app = QApplication.instance() or QApplication([])
    dlg = RecipesDialog(presenter, product_id=_PROD, product_name="Prod")
    assert dlg.recipes_table.rowCount() == 1


def test_recipe_form_dialog_creates(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.recipe_form_dialog import (
        RecipeFormDialog,
    )
    app = QApplication.instance() or QApplication([])
    dlg = RecipeFormDialog(presenter, product_id=_PROD)
    dlg.name.setText("Mi receta")
    dlg._components = [{"component_product_id": "c1", "quantity": "3", "unit_id": "u"}]
    dlg._refresh_table()
    dlg._on_save()
    assert presenter.list_recipes(_PROD)[0]["name"] == "Mi receta"

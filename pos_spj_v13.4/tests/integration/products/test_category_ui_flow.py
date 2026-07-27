"""P1-01 — flujo presenter/UI de categorías: alta desde el árbol, selector en form."""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.catalog_read_service import (  # noqa: E402
    ProductCatalogReadService,
)
from backend.application.products.queries.product_category_query_service import (  # noqa: E402
    ProductCategoryQueryService,
)
from backend.application.products.use_cases.product_category_use_cases import (  # noqa: E402
    CreateProductCategoryUseCase,
    MoveProductCategoryUseCase,
    SetProductCategoryActiveUseCase,
    UpdateProductCategoryUseCase,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from frontend.desktop.modules.products.presenter import ProductsPresenter  # noqa: E402


class _Session:
    user_id = "u1"


@pytest.fixture
def presenter():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_products_schema(conn)
    conn.commit()

    def categories_write_factory():
        return {
            "create": CreateProductCategoryUseCase(conn),
            "edit": UpdateProductCategoryUseCase(conn),
            "move": MoveProductCategoryUseCase(conn),
            "set_active": SetProductCategoryActiveUseCase(conn),
        }

    p = ProductsPresenter(
        read_service_factory=lambda: ProductCatalogReadService(conn),
        categories_read_factory=lambda: ProductCategoryQueryService(conn),
        categories_write_factory=categories_write_factory,
        session_context=_Session())
    p._conn = conn
    yield p
    conn.close()


def test_presenter_can_manage_categories(presenter):
    assert presenter.can_manage_categories is True


def test_save_category_root_then_child(presenter):
    ok, _msg, root_id = presenter.save_category(
        category_id=None, code="CARN", name="Carnes")
    assert ok and root_id
    ok2, _m2, child_id = presenter.save_category(
        category_id=None, code="RES", name="Res", parent_id=root_id)
    assert ok2 and child_id
    tree = presenter.category_tree()
    assert tree[0]["code"] == "CARN"
    assert tree[0]["children"][0]["code"] == "RES"


def test_list_categories_feeds_selector(presenter):
    _ok, _m, root_id = presenter.save_category(
        category_id=None, code="CARN", name="Carnes")
    presenter.save_category(category_id=None, code="RES", name="Res", parent_id=root_id)
    opts = presenter.list_categories()
    ids = {o["id"] for o in opts}
    assert root_id in ids and len(opts) == 2


def test_page_builds_tree(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.pages.categories_page import (
        ProductCategoriesPage,
    )
    _ok, _m, root_id = presenter.save_category(
        category_id=None, code="CARN", name="Carnes")
    presenter.save_category(category_id=None, code="RES", name="Res", parent_id=root_id)
    app = QApplication.instance() or QApplication([])
    page = ProductCategoriesPage(presenter)
    assert page.tree.topLevelItemCount() == 1
    root_item = page.tree.topLevelItem(0)
    assert root_item.text(1) == "CARN" and root_item.childCount() == 1
    assert root_item.child(0).text(1) == "RES"


def test_category_form_dialog_saves(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.category_form_dialog import (
        CategoryFormDialog,
    )
    app = QApplication.instance() or QApplication([])
    dlg = CategoryFormDialog(presenter, category=None)
    dlg.code.setText("carn")
    dlg.name.setText("Carnes")
    dlg._on_save()
    assert presenter.category_tree()[0]["code"] == "CARN"


def test_product_form_category_selector_stores_id(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.product_form_dialog import (
        ProductFormDialog,
    )
    _ok, _m, root_id = presenter.save_category(
        category_id=None, code="CARN", name="Carnes")
    # El form necesita el factory de escritura de producto para habilitar el guardado;
    # aquí sólo probamos que el selector expone el id de la categoría.
    app = QApplication.instance() or QApplication([])
    dlg = ProductFormDialog(presenter, product_id=None)
    idx = dlg.category.findData(root_id)
    assert idx >= 0
    dlg.category.setCurrentIndex(idx)
    assert dlg._fields()["category_id"] == root_id

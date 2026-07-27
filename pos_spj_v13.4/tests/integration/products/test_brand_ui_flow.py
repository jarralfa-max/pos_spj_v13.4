"""P1-02 — flujo presenter/UI de marcas: gestión + selector en el formulario."""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.catalog_read_service import (  # noqa: E402
    ProductCatalogReadService,
)
from backend.application.products.queries.product_brand_query_service import (  # noqa: E402
    ProductBrandQueryService,
)
from backend.application.products.use_cases.product_brand_use_cases import (  # noqa: E402
    CreateProductBrandUseCase,
    SetProductBrandActiveUseCase,
    UpdateProductBrandUseCase,
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

    def brands_write_factory():
        return {
            "create": CreateProductBrandUseCase(conn),
            "edit": UpdateProductBrandUseCase(conn),
            "set_active": SetProductBrandActiveUseCase(conn),
        }

    p = ProductsPresenter(
        read_service_factory=lambda: ProductCatalogReadService(conn),
        brands_read_factory=lambda: ProductBrandQueryService(conn),
        brands_write_factory=brands_write_factory,
        session_context=_Session())
    p._conn = conn
    yield p
    conn.close()


def test_presenter_can_manage_brands(presenter):
    assert presenter.can_manage_brands is True


def test_save_brand_and_list(presenter):
    ok, _msg, bid = presenter.save_brand(
        brand_id=None, code="BIM", name="Bimbo", description="Panadería")
    assert ok and bid
    catalog = presenter.brand_catalog()
    assert catalog[0]["code"] == "BIM" and catalog[0]["description"] == "Panadería"


def test_list_brands_feeds_selector(presenter):
    presenter.save_brand(brand_id=None, code="BIM", name="Bimbo")
    presenter.save_brand(brand_id=None, code="LAL", name="Lala")
    opts = presenter.list_brands()
    assert {o["code"] for o in opts} == {"BIM", "LAL"}
    assert all(o["id"] and o["label"] for o in opts)


def test_page_lists_brands(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.pages.brands_page import ProductBrandsPage
    presenter.save_brand(brand_id=None, code="BIM", name="Bimbo")
    app = QApplication.instance() or QApplication([])
    page = ProductBrandsPage(presenter)
    assert page.table.rowCount() == 1


def test_brand_form_dialog_saves(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.brand_form_dialog import (
        BrandFormDialog,
    )
    app = QApplication.instance() or QApplication([])
    dlg = BrandFormDialog(presenter, brand=None)
    dlg.code.setText("bim")
    dlg.name.setText("Bimbo")
    dlg._on_save()
    assert presenter.brand_catalog()[0]["code"] == "BIM"


def test_product_form_brand_selector_stores_id(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.product_form_dialog import (
        ProductFormDialog,
    )
    _ok, _m, bid = presenter.save_brand(brand_id=None, code="BIM", name="Bimbo")
    app = QApplication.instance() or QApplication([])
    dlg = ProductFormDialog(presenter, product_id=None)
    idx = dlg.brand.findData(bid)
    assert idx >= 0
    dlg.brand.setCurrentIndex(idx)
    assert dlg._fields()["brand_id"] == bid

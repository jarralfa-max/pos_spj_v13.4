"""P1-03 — flujo presenter/UI de atributos: gestión + opciones."""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.catalog_read_service import (  # noqa: E402
    ProductCatalogReadService,
)
from backend.application.products.queries.product_attribute_query_service import (  # noqa: E402
    ProductAttributeQueryService,
)
from backend.application.products.use_cases.product_attribute_use_cases import (  # noqa: E402
    AddAttributeOptionUseCase,
    CreateProductAttributeUseCase,
    SetProductAttributeActiveUseCase,
    UpdateAttributeOptionUseCase,
    UpdateProductAttributeUseCase,
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

    def attributes_write_factory():
        return {
            "create": CreateProductAttributeUseCase(conn),
            "update": UpdateProductAttributeUseCase(conn),
            "set_active": SetProductAttributeActiveUseCase(conn),
            "add_option": AddAttributeOptionUseCase(conn),
            "update_option": UpdateAttributeOptionUseCase(conn),
        }

    p = ProductsPresenter(
        read_service_factory=lambda: ProductCatalogReadService(conn),
        attributes_read_factory=lambda: ProductAttributeQueryService(conn),
        attributes_write_factory=attributes_write_factory,
        session_context=_Session())
    p._conn = conn
    yield p
    conn.close()


def test_presenter_can_manage_attributes(presenter):
    assert presenter.can_manage_attributes is True


def test_save_attribute_and_options(presenter):
    ok, _msg, aid = presenter.save_attribute(
        attribute_id=None, code="COL", name="Color", data_type="LIST")
    assert ok and aid
    ok2, _m2, oid = presenter.save_attribute_option(
        option_id=None, attribute_id=aid, code="ROJ", label="Rojo")
    assert ok2 and oid
    options = presenter.list_attribute_options(aid)
    assert [o["code"] for o in options] == ["ROJ"]


def test_page_lists_attributes(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.pages.attributes_page import (
        ProductAttributesPage,
    )
    presenter.save_attribute(attribute_id=None, code="COL", name="Color")
    app = QApplication.instance() or QApplication([])
    page = ProductAttributesPage(presenter)
    assert page.table.rowCount() == 1


def test_attribute_form_dialog_saves(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.attribute_form_dialog import (
        AttributeFormDialog,
    )
    app = QApplication.instance() or QApplication([])
    dlg = AttributeFormDialog(presenter, attribute=None)
    dlg.code.setText("col")
    dlg.name.setText("Color")
    dlg._select(dlg.data_type, "LIST")
    dlg._on_save()
    assert presenter.attribute_catalog()[0]["code"] == "COL"


def test_options_dialog_lists_and_adds(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.attribute_form_dialog import (
        AttributeOptionsDialog,
    )
    _ok, _m, aid = presenter.save_attribute(
        attribute_id=None, code="COL", name="Color", data_type="LIST")
    presenter.save_attribute_option(option_id=None, attribute_id=aid, code="ROJ",
                                    label="Rojo")
    app = QApplication.instance() or QApplication([])
    dlg = AttributeOptionsDialog(presenter, attribute=presenter.get_attribute(aid))
    assert dlg.table.rowCount() == 1 and dlg._is_list

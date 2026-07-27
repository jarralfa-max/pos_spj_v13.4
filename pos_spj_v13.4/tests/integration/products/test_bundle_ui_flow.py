"""Combos UI — flujo presenter/diálogos: crear combo y listar versiones."""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.catalog_read_service import (  # noqa: E402
    ProductCatalogReadService,
)
from backend.application.products.queries.product_bundle_query_service import (  # noqa: E402
    ProductBundleQueryService,
)
from backend.application.products.use_cases.product_bundle_use_cases import (  # noqa: E402
    ActivateBundleVersionUseCase,
    ApproveBundleVersionUseCase,
    CreateProductBundleUseCase,
    SubmitBundleVersionUseCase,
    UpdateBundleVersionUseCase,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from frontend.desktop.modules.products.presenter import ProductsPresenter  # noqa: E402

_PROD = "combo-1"


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
        bundles_read_factory=lambda: ProductBundleQueryService(conn),
        bundles_write_factory=lambda: {
            "create": CreateProductBundleUseCase(conn),
            "update": UpdateBundleVersionUseCase(conn),
            "submit": SubmitBundleVersionUseCase(conn),
            "approve": ApproveBundleVersionUseCase(conn),
            "activate": ActivateBundleVersionUseCase(conn),
        },
        session_context=_Session())
    p._conn = conn
    yield p
    conn.close()


_COMP = [{"component_product_id": "refresco", "quantity": "1", "unit_id": "pza"}]


def test_presenter_can_manage_bundles(presenter):
    assert presenter.can_manage_bundles is True


def test_create_and_list_bundle(presenter):
    ok, _msg = presenter.create_bundle(
        product_id=_PROD, bundle_type="FIXED_COMBO", name="Combo", components=_COMP)
    assert ok
    bundles = presenter.list_bundles(_PROD)
    assert bundles[0]["name"] == "Combo"
    versions = presenter.list_bundle_versions(bundles[0]["id"])
    assert versions[0]["status"] == "DRAFT"


def test_dialog_lists_bundles(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.bundles_dialog import BundlesDialog
    presenter.create_bundle(product_id=_PROD, bundle_type="FIXED_COMBO", name="Combo",
                            components=_COMP)
    app = QApplication.instance() or QApplication([])
    dlg = BundlesDialog(presenter, product_id=_PROD, product_name="Combo")
    assert dlg.bundles_table.rowCount() == 1


def test_bundle_form_dialog_creates(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.bundle_form_dialog import (
        BundleFormDialog,
    )
    app = QApplication.instance() or QApplication([])
    dlg = BundleFormDialog(presenter, product_id=_PROD)
    dlg.name.setText("Mi combo")
    dlg._components = list(_COMP)
    dlg._refresh_table()
    dlg._on_save()
    assert presenter.list_bundles(_PROD)[0]["name"] == "Mi combo"

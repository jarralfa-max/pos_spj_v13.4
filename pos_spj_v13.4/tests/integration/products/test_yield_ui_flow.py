"""Rendimientos UI — flujo presenter/diálogos: crear perfil y listar versiones."""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.catalog_read_service import (  # noqa: E402
    ProductCatalogReadService,
)
from backend.application.products.queries.product_yield_query_service import (  # noqa: E402
    ProductYieldQueryService,
)
from backend.application.products.use_cases.product_yield_use_cases import (  # noqa: E402
    ActivateYieldVersionUseCase,
    ApproveYieldVersionUseCase,
    CreateYieldProfileUseCase,
    SubmitYieldVersionUseCase,
    UpdateYieldVersionUseCase,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from frontend.desktop.modules.products.presenter import ProductsPresenter  # noqa: E402

_PROD = "carcass-1"


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
        yields_read_factory=lambda: ProductYieldQueryService(conn),
        yields_write_factory=lambda: {
            "create": CreateYieldProfileUseCase(conn),
            "edit": UpdateYieldVersionUseCase(conn),
            "submit": SubmitYieldVersionUseCase(conn),
            "approve": ApproveYieldVersionUseCase(conn),
            "activate": ActivateYieldVersionUseCase(conn),
        },
        session_context=_Session())
    p._conn = conn
    yield p
    conn.close()


_OUT = [{"product_id": "lomo", "output_type": "MAIN_PRODUCT",
         "expected_yield_pct": "100", "unit_id": "u"}]


def test_presenter_can_manage_yields(presenter):
    assert presenter.can_manage_yields is True


def test_create_and_list_yield(presenter):
    ok, _msg = presenter.create_yield_profile(
        input_product_id=_PROD, name="Rend", tolerance_pct="0", outputs=_OUT)
    assert ok
    profiles = presenter.list_yield_profiles(_PROD)
    assert profiles[0]["name"] == "Rend"
    versions = presenter.list_yield_versions(profiles[0]["id"])
    assert versions[0]["status"] == "DRAFT"


def test_dialog_lists_profiles(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.yields_dialog import (
        YieldProfilesDialog,
    )
    presenter.create_yield_profile(input_product_id=_PROD, name="Rend",
                                   tolerance_pct="0", outputs=_OUT)
    app = QApplication.instance() or QApplication([])
    dlg = YieldProfilesDialog(presenter, product_id=_PROD, product_name="Canal")
    assert dlg.profiles_table.rowCount() == 1


def test_yield_form_dialog_creates(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.yield_form_dialog import (
        YieldProfileFormDialog,
    )
    app = QApplication.instance() or QApplication([])
    dlg = YieldProfileFormDialog(presenter, input_product_id=_PROD)
    dlg.name.setText("Mi rendimiento")
    dlg.tolerance.setValue(0)
    dlg._outputs = list(_OUT)
    dlg._refresh_table()
    dlg._on_save()
    assert presenter.list_yield_profiles(_PROD)[0]["name"] == "Mi rendimiento"

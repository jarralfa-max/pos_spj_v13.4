"""Despiece UI — flujo presenter/diálogos: crear esquema y listar versiones."""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.catalog_read_service import (  # noqa: E402
    ProductCatalogReadService,
)
from backend.application.products.queries.product_cutting_query_service import (  # noqa: E402
    ProductCuttingQueryService,
)
from backend.application.products.use_cases.product_cutting_use_cases import (  # noqa: E402
    ActivateCuttingVersionUseCase,
    ApproveCuttingVersionUseCase,
    CreateCuttingSchemeUseCase,
    SubmitCuttingVersionUseCase,
    UpdateCuttingVersionUseCase,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from frontend.desktop.modules.products.presenter import ProductsPresenter  # noqa: E402

_PROD = "canal-1"


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
        cutting_read_factory=lambda: ProductCuttingQueryService(conn),
        cutting_write_factory=lambda: {
            "create": CreateCuttingSchemeUseCase(conn),
            "update": UpdateCuttingVersionUseCase(conn),
            "submit": SubmitCuttingVersionUseCase(conn),
            "approve": ApproveCuttingVersionUseCase(conn),
            "activate": ActivateCuttingVersionUseCase(conn),
        },
        session_context=_Session())
    p._conn = conn
    yield p
    conn.close()


_OUT = [{"product_id": "lomo", "measure_kind": "BY_WEIGHT", "quantity": "10",
         "unit_id": "u"}]


def test_presenter_can_manage_cutting(presenter):
    assert presenter.can_manage_cutting is True


def test_create_and_list_cutting(presenter):
    ok, _msg = presenter.create_cutting_scheme(
        input_product_id=_PROD, species_id="bovino", name="Despiece",
        cut_level="PRIMARY", outputs=_OUT)
    assert ok
    schemes = presenter.list_cutting_schemes(_PROD)
    assert schemes[0]["name"] == "Despiece"
    versions = presenter.list_cutting_versions(schemes[0]["id"])
    assert versions[0]["status"] == "DRAFT"


def test_dialog_lists_schemes(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.cutting_dialog import (
        CuttingSchemesDialog,
    )
    presenter.create_cutting_scheme(input_product_id=_PROD, species_id="bovino",
                                    name="Despiece", cut_level="PRIMARY", outputs=_OUT)
    app = QApplication.instance() or QApplication([])
    dlg = CuttingSchemesDialog(presenter, product_id=_PROD, product_name="Canal",
                               species_id="bovino")
    assert dlg.schemes_table.rowCount() == 1


def test_cutting_form_dialog_creates(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.cutting_form_dialog import (
        CuttingSchemeFormDialog,
    )
    app = QApplication.instance() or QApplication([])
    dlg = CuttingSchemeFormDialog(presenter, input_product_id=_PROD,
                                  species_id="bovino")
    dlg.name.setText("Mi despiece")
    dlg._outputs = list(_OUT)
    dlg._refresh_table()
    dlg._on_save()
    assert presenter.list_cutting_schemes(_PROD)[0]["name"] == "Mi despiece"

"""PROD-19 paso 7b — flujo presenter/host: alta escribe canónico y aparece en catálogo."""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.catalog_read_service import (  # noqa: E402
    ProductCatalogReadService,
)
from backend.application.products.use_cases.product_master_use_cases import (  # noqa: E402
    CreateProductMasterUseCase,
    UpdateProductMasterUseCase,
)
from backend.infrastructure.db.repositories.products.product_master_repository import (  # noqa: E402
    ProductMasterRepository,
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

    def write_factory():
        return (CreateProductMasterUseCase(conn), UpdateProductMasterUseCase(conn),
                ProductMasterRepository(conn))

    p = ProductsPresenter(
        read_service_factory=lambda: ProductCatalogReadService(conn),
        write_service_factory=write_factory, session_context=_Session())
    p._conn = conn
    yield p
    conn.close()


_FIELDS = dict(code="A-1", name="Bistec", short_name=None, product_type="RAW_MATERIAL",
               base_unit_id="KG", lifecycle_status="ACTIVE", sellable=True,
               purchasable=True, inventory_managed=True, producible=False,
               internal_only=False, recipe_allowed=False, bundle_allowed=False,
               lot_controlled=False, expiration_controlled=False,
               catch_weight_enabled=False, quality_controlled=False,
               traceability_required=False)


def test_presenter_can_write(presenter):
    assert presenter.can_write is True


def test_create_appears_in_catalog(presenter):
    ok, msg, pid = presenter.save_product(product_id=None, fields=dict(_FIELDS))
    assert ok and pid
    rows = presenter.catalog().rows
    assert any("A-1" in r[0] for r in rows)  # aparece de inmediato (mismo maestro)


def test_edit_prefill_and_update(presenter):
    ok, _msg, pid = presenter.save_product(product_id=None, fields=dict(_FIELDS))
    assert ok
    row = presenter.get_product(pid)
    assert row["code"] == "A-1"
    ok2, _m2, _pid2 = presenter.save_product(
        product_id=pid, fields={**_FIELDS, "name": "Bistec Premium"})
    assert ok2
    assert presenter.get_product(pid)["name"] == "Bistec Premium"


def test_duplicate_code_surfaces_error(presenter):
    presenter.save_product(product_id=None, fields=dict(_FIELDS))
    ok, msg, pid = presenter.save_product(product_id=None,
                                          fields={**_FIELDS, "name": "Otro"})
    assert not ok and pid is None and "ya existe" in msg


def test_dialog_constructs_and_reads_fields(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.product_form_dialog import (
        ProductFormDialog,
    )
    app = QApplication.instance() or QApplication([])
    dlg = ProductFormDialog(presenter, product_id=None)
    dlg.code.setText("Z-9")
    dlg.name.setText("Producto Z")
    dlg.base_unit.setText("pza")
    f = dlg._fields()
    assert f["code"] == "Z-9" and f["base_unit_id"] == "PZA" and f["name"] == "Producto Z"

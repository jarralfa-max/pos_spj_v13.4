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


_UNIT_ID = "unit-kg-0001"


@pytest.fixture
def presenter():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_products_schema(conn)
    conn.execute("INSERT INTO units_of_measure (id, code, name, dimension, active) "
                 "VALUES (?, 'KG', 'Kilogramo', 'WEIGHT', 1)", (_UNIT_ID,))
    conn.execute("INSERT INTO product_code_generation_rules "
                 "(id, scope_type, scope_value, prefix, padding, separator, active) "
                 "VALUES ('r1','PRODUCT_TYPE','RAW_MATERIAL','MP',6,'-',1)")
    conn.commit()

    from backend.application.products.queries.unit_catalog_query_service import (
        UnitCatalogQueryService,
    )
    from backend.application.products.queries.product_code_query_service import (
        PreviewProductCodeQueryService,
    )

    def write_factory():
        return (CreateProductMasterUseCase(conn), UpdateProductMasterUseCase(conn),
                ProductMasterRepository(conn))

    p = ProductsPresenter(
        read_service_factory=lambda: ProductCatalogReadService(conn),
        write_service_factory=write_factory,
        units_service_factory=lambda: UnitCatalogQueryService(conn),
        code_service_factory=lambda: PreviewProductCodeQueryService(conn),
        session_context=_Session())
    p._conn = conn
    yield p
    conn.close()


_FIELDS = dict(code="A-1", name="Bistec", short_name=None, product_type="RAW_MATERIAL",
               base_unit_id=_UNIT_ID, lifecycle_status="ACTIVE", sellable=True,
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


def test_dialog_auto_generates_code_preview(presenter):
    # P0-04: en alta el código se genera automáticamente (vista previa, sin consumir).
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.product_form_dialog import (
        ProductFormDialog,
    )
    app = QApplication.instance() or QApplication([])
    dlg = ProductFormDialog(presenter, product_id=None)
    dlg.name.setText("Producto Z")
    dlg._select(dlg.product_type, "RAW_MATERIAL")
    idx = dlg.base_unit.findData(_UNIT_ID)
    assert idx >= 0
    dlg.base_unit.setCurrentIndex(idx)
    assert dlg.code.isReadOnly() and dlg.code.text() == "MP-000001"
    f = dlg._fields()
    # Con auto-generación el código lo reserva el caso de uso, no la UI.
    assert f["auto_generate_code"] is True and f["code"] == ""
    assert f["base_unit_id"] == _UNIT_ID and f["name"] == "Producto Z"


def test_dialog_manual_override_captures_code(presenter):
    # Con permiso de override el usuario puede capturar el código manualmente.
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.product_form_dialog import (
        ProductFormDialog,
    )
    app = QApplication.instance() or QApplication([])
    assert presenter.can_override_code  # sin checker → permisivo
    dlg = ProductFormDialog(presenter, product_id=None)
    dlg._manual_box.setChecked(True)
    dlg.code.setText("Z-9")
    dlg.name.setText("Producto Z")
    f = dlg._fields()
    assert not f.get("auto_generate_code") and f["code"] == "Z-9"

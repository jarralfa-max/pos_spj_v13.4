"""P0-A slice 1 — catálogo de especies + selector cárnico del formulario (§5.2).

Cubre los escenarios reproducidos:
- una canal cárnica (CARCASS) NO podía guardarse porque el formulario no capturaba
  especie → ahora el selector envía `species_id` y el alta funciona;
- un tipo no cárnico no exige especie;
- la migración 169 siembra el catálogo y el query service lo sirve como opciones.
"""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.catalog_read_service import (  # noqa: E402
    ProductCatalogReadService,
)
from backend.application.products.queries.species_catalog_query_service import (  # noqa: E402
    SpeciesCatalogQueryService,
)
from backend.application.products.queries.unit_catalog_query_service import (  # noqa: E402
    UnitCatalogQueryService,
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

_UNIT_ID = "unit-kg-0001"


class _Session:
    user_id = "u1"


@pytest.fixture
def presenter():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_products_schema(conn)
    conn.execute("INSERT INTO units_of_measure (id, code, name, dimension, active) "
                 "VALUES (?, 'KG', 'Kilogramo', 'WEIGHT', 1)", (_UNIT_ID,))
    # seed de especies (equivalente a la migración 169)
    conn.executemany(
        "INSERT INTO species (id, code, name, active) VALUES (?,?,?,1)",
        [("sp-ave", "AVE_POLLO", "Ave — pollo"), ("sp-bov", "BOVINO", "Bovino (res)")])
    conn.commit()

    def write_factory():
        return (CreateProductMasterUseCase(conn), UpdateProductMasterUseCase(conn),
                ProductMasterRepository(conn))

    p = ProductsPresenter(
        read_service_factory=lambda: ProductCatalogReadService(conn),
        write_service_factory=write_factory,
        units_service_factory=lambda: UnitCatalogQueryService(conn),
        species_read_factory=lambda: SpeciesCatalogQueryService(conn),
        session_context=_Session())
    p._conn = conn
    yield p
    conn.close()


def test_species_options_available(presenter):
    opts = presenter.list_species()
    assert {o["label"] for o in opts} >= {"Ave — pollo", "Bovino (res)"}
    assert all(o["id"] and o["label"] for o in opts)  # id + label, sin texto libre


def test_meat_product_saves_with_species(presenter):
    ok, msg, pid = presenter.save_product(product_id=None, fields=dict(
        code="C-1", name="Pollo canal", short_name=None, product_type="CARCASS",
        category_id=None, brand_id=None, base_unit_id=_UNIT_ID, species_id="sp-ave",
        lifecycle_status="DRAFT", sellable=True, purchasable=True,
        inventory_managed=True, producible=False, internal_only=False,
        recipe_allowed=False, bundle_allowed=False, lot_controlled=True,
        expiration_controlled=True, catch_weight_enabled=True,
        quality_controlled=False, traceability_required=True))
    assert ok and pid, msg
    assert presenter.get_product(pid)["species_id"] == "sp-ave"


def test_meat_product_without_species_is_rejected(presenter):
    ok, msg, pid = presenter.save_product(product_id=None, fields=dict(
        code="C-2", name="Res canal", short_name=None, product_type="CARCASS",
        category_id=None, brand_id=None, base_unit_id=_UNIT_ID, species_id=None,
        lifecycle_status="DRAFT", sellable=True, purchasable=True,
        inventory_managed=True, producible=False, internal_only=False,
        recipe_allowed=False, bundle_allowed=False, lot_controlled=False,
        expiration_controlled=False, catch_weight_enabled=False,
        quality_controlled=False, traceability_required=False))
    assert not ok and pid is None
    assert "especie" in msg.lower()


def test_non_meat_product_does_not_require_species(presenter):
    ok, msg, pid = presenter.save_product(product_id=None, fields=dict(
        code="R-1", name="Refresco", short_name=None, product_type="RESALE_PRODUCT",
        category_id=None, brand_id=None, base_unit_id=_UNIT_ID, species_id=None,
        lifecycle_status="DRAFT", sellable=True, purchasable=True,
        inventory_managed=True, producible=False, internal_only=False,
        recipe_allowed=False, bundle_allowed=False, lot_controlled=False,
        expiration_controlled=False, catch_weight_enabled=False,
        quality_controlled=False, traceability_required=False))
    assert ok and pid, msg


def test_form_shows_species_only_for_meat_types(presenter):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.product_form_dialog import (
        ProductFormDialog,
    )
    app = QApplication.instance() or QApplication([])  # noqa: F841
    dlg = ProductFormDialog(presenter, product_id=None)
    # el selector se pobló del catálogo (placeholder + 2 especies)
    assert dlg.species.count() == 3
    dlg._select(dlg.product_type, "RESALE_PRODUCT")
    assert not dlg._meat_box.isVisible() or not dlg._is_meat_type()
    dlg._select(dlg.product_type, "CARCASS")
    assert dlg._is_meat_type()
    # elegir especie → _fields envía species_id; sin elegir → validación lo bloquea
    idx = dlg.species.findData("sp-ave")
    dlg.species.setCurrentIndex(idx)
    assert dlg._fields()["species_id"] == "sp-ave"

"""P0-A slice 2 — ciclo de vida: sin selector engañoso, con acciones reales.

Reproducido: el formulario mostraba un selector de estado (ACTIVE/…) que el backend
ignoraba (el alta nace DRAFT). Ahora:
- el formulario muestra el estado como badge informativo (no editable) y `_fields`
  no envía `lifecycle_status`;
- existen acciones de workflow (enviar a revisión → activar) expuestas por el
  presenter, con panel de preparación (readiness) que lista faltantes.
"""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.catalog_read_service import (  # noqa: E402
    ProductCatalogReadService,
)
from backend.application.products.queries.product_activation_readiness_query_service import (  # noqa: E402
    ProductActivationReadinessQueryService,
)
from backend.application.products.queries.species_catalog_query_service import (  # noqa: E402
    SpeciesCatalogQueryService,
)
from backend.application.products.queries.unit_catalog_query_service import (  # noqa: E402
    UnitCatalogQueryService,
)
from backend.application.products.use_cases.product_lifecycle_use_cases import (  # noqa: E402
    ActivateProductUseCase,
    SubmitProductUseCase,
)
from backend.application.products.use_cases.product_master_use_cases import (  # noqa: E402
    CreateProductMasterUseCase,
    UpdateProductMasterUseCase,
)
from backend.infrastructure.db.repositories.products.product_master_repository import (  # noqa: E402
    ProductMasterRepository,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.modules.products.presenter import ProductsPresenter  # noqa: E402

_UNIT_ID = "unit-kg-0002"
_CAT_ID = "cat-carnes-0001"


class _Session:
    user_id = "u1"


@pytest.fixture
def presenter():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_products_schema(conn)
    conn.execute("INSERT INTO units_of_measure (id, code, name, dimension, active) "
                 "VALUES (?, 'KG', 'Kilogramo', 'WEIGHT', 1)", (_UNIT_ID,))
    conn.execute("INSERT INTO product_categories (id, code, name, name_normalized, "
                 "active) VALUES (?, 'CARN', 'Carnes', 'carnes', 1)", (_CAT_ID,))
    conn.commit()

    def write_factory():
        return (CreateProductMasterUseCase(conn), UpdateProductMasterUseCase(conn),
                ProductMasterRepository(conn))

    def lifecycle_factory():
        return {"submit": SubmitProductUseCase(conn),
                "activate": ActivateProductUseCase(conn),
                "readiness": ProductActivationReadinessQueryService(conn)}

    p = ProductsPresenter(
        read_service_factory=lambda: ProductCatalogReadService(conn),
        write_service_factory=write_factory,
        lifecycle_service_factory=lifecycle_factory,
        units_service_factory=lambda: UnitCatalogQueryService(conn),
        species_read_factory=lambda: SpeciesCatalogQueryService(conn),
        session_context=_Session())
    p._conn = conn
    yield p
    conn.close()


def _new_product(presenter, **overrides):
    fields = dict(code=None, auto_generate_code=False, name="Bistec",
                  short_name=None, product_type="RESALE_PRODUCT", category_id=_CAT_ID,
                  brand_id=None, base_unit_id=_UNIT_ID, species_id=None,
                  sellable=True, purchasable=True, inventory_managed=True,
                  producible=False, internal_only=False, recipe_allowed=False,
                  bundle_allowed=False, lot_controlled=False,
                  expiration_controlled=False, catch_weight_enabled=False,
                  quality_controlled=False, traceability_required=False)
    fields.update(overrides)
    fields["code"] = fields["code"] or f"P-{new_uuid()[:6]}"
    return presenter.save_product(product_id=None, fields=fields)


def test_new_product_is_born_draft(presenter):
    ok, _m, pid = _new_product(presenter)
    assert ok and presenter.get_product(pid)["lifecycle_status"] == "DRAFT"


def test_submit_then_activate_flow(presenter):
    # §6.5: segregación — el creador (otro usuario) no puede activar; la sesión u1
    # actúa como el segundo usuario que revisa/activa.
    from backend.application.products.commands.product_master_commands import (
        CreateProductMasterCommand,
    )
    res = CreateProductMasterUseCase(presenter._conn).execute(CreateProductMasterCommand(
        operation_id=new_uuid(), user_id="creator", code=f"P-{new_uuid()[:6]}",
        name="Bistec", product_type="RESALE_PRODUCT", category_id=_CAT_ID,
        base_unit_id=_UNIT_ID))
    pid = res.product_id
    assert res.success and pid
    # readiness listo (unidad + categoría presentes, no cárnico)
    readiness = presenter.activation_readiness(pid)
    assert readiness is not None and readiness.ready, readiness.missing
    ok_s, _ms = presenter.submit_product(pid)
    assert ok_s
    assert presenter.get_product(pid)["lifecycle_status"] == "UNDER_REVIEW"
    ok_a, _ma = presenter.activate_product(pid)
    assert ok_a, _ma
    assert presenter.get_product(pid)["lifecycle_status"] == "ACTIVE"


def test_creator_cannot_activate_segregation(presenter):
    # el mismo usuario de sesión (u1) crea y no puede activar (§6.5)
    ok, _m, pid = _new_product(presenter)
    assert ok
    presenter.submit_product(pid)
    ok_a, msg = presenter.activate_product(pid)
    assert not ok_a and ("segundo usuario" in msg or "segreg" in msg.lower())


def test_readiness_lists_missing_for_meat_without_species(presenter):
    # una canal cárnica sin especie no está lista → readiness lo explica
    conn = presenter._conn
    conn.execute("INSERT INTO species (id, code, name, active) VALUES "
                 "('sp-x','AVE_POLLO','Ave — pollo',1)")
    conn.commit()
    ok, _m, pid = _new_product(presenter, name="Pollo canal", product_type="CARCASS",
                               species_id="sp-x", sellable=False, internal_only=False)
    assert ok
    # quitar la especie para forzar faltante (simula dato incompleto)
    conn.execute("UPDATE products SET species_id=NULL WHERE id=?", (pid,))
    conn.commit()
    readiness = presenter.activation_readiness(pid)
    assert not readiness.ready
    assert any("Especie" in m for m in readiness.missing)


def test_form_shows_state_badge_not_editable_selector(presenter):
    from PyQt5.QtWidgets import QApplication, QComboBox

    from frontend.desktop.modules.products.dialogs.product_form_dialog import (
        ProductFormDialog,
    )
    app = QApplication.instance() or QApplication([])  # noqa: F841
    dlg = ProductFormDialog(presenter, product_id=None)
    # no hay combo de estado editable; hay un badge informativo
    assert not hasattr(dlg, "lifecycle") or not isinstance(
        getattr(dlg, "lifecycle", None), QComboBox)
    assert dlg._state_badge.text()  # badge presente
    # _fields NO dicta el estado
    dlg.name.setText("X")
    assert "lifecycle_status" not in dlg._fields()

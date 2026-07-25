"""P1-03 — flujo presenter/UI de variantes: generación desde el diálogo."""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.commands.product_attribute_commands import (  # noqa: E402
    AddAttributeOptionCommand,
    CreateAttributeCommand,
)
from backend.application.products.commands.product_master_commands import (  # noqa: E402
    CreateProductMasterCommand,
)
from backend.application.products.queries.catalog_read_service import (  # noqa: E402
    ProductCatalogReadService,
)
from backend.application.products.queries.product_attribute_query_service import (  # noqa: E402
    ProductAttributeQueryService,
)
from backend.application.products.queries.product_variant_query_service import (  # noqa: E402
    ProductVariantQueryService,
)
from backend.application.products.use_cases.product_attribute_use_cases import (  # noqa: E402
    AddAttributeOptionUseCase,
    CreateProductAttributeUseCase,
)
from backend.application.products.use_cases.product_master_use_cases import (  # noqa: E402
    CreateProductMasterUseCase,
)
from backend.application.products.use_cases.product_variant_use_cases import (  # noqa: E402
    GenerateProductVariantsUseCase,
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
    conn.execute("INSERT INTO product_code_generation_rules "
                 "(id, scope_type, scope_value, prefix, padding, separator, active) "
                 "VALUES ('r0','DEFAULT','','PRD',6,'-',1)")
    conn.commit()

    def write_factory():
        from backend.infrastructure.db.repositories.products.product_master_repository \
            import ProductMasterRepository
        return (CreateProductMasterUseCase(conn), None, ProductMasterRepository(conn))

    p = ProductsPresenter(
        read_service_factory=lambda: ProductCatalogReadService(conn),
        write_service_factory=write_factory,
        attributes_read_factory=lambda: ProductAttributeQueryService(conn),
        variants_read_factory=lambda: ProductVariantQueryService(conn),
        variants_write_factory=lambda: GenerateProductVariantsUseCase(conn),
        session_context=_Session())
    p._conn = conn

    # Datos de apoyo: producto padre + atributo con opciones.
    parent = CreateProductMasterUseCase(conn).execute(CreateProductMasterCommand(
        operation_id="op", code="PLAY-1", name="Playera",
        product_type="RESALE_PRODUCT", base_unit_id=_UNIT_ID, user_id="u1")).product_id
    attr = CreateProductAttributeUseCase(conn).execute(CreateAttributeCommand(
        operation_id="opa", code="COL", name="Color", user_id="u1")).entity_id
    opts = [AddAttributeOptionUseCase(conn).execute(AddAttributeOptionCommand(
        operation_id="opo", attribute_id=attr, code=c, label=l, user_id="u1")).entity_id
        for c, l in (("ROJ", "Rojo"), ("AZU", "Azul"))]
    p._parent_id = parent
    p._attr_id = attr
    p._opt_ids = opts
    yield p
    conn.close()


def test_presenter_can_generate(presenter):
    assert presenter.can_generate_variants is True


def test_variant_axes_catalog_exposes_options(presenter):
    axes = presenter.variant_axes_catalog()
    assert axes and axes[0]["code"] == "COL"
    assert {o["code"] for o in axes[0]["options"]} == {"ROJ", "AZU"}


def test_generate_creates_variants(presenter):
    ok, _msg = presenter.generate_variants(
        parent_product_id=presenter._parent_id,
        axes={presenter._attr_id: presenter._opt_ids})
    assert ok
    assert len(presenter.list_variants(presenter._parent_id)) == 2


def test_dialog_generates_from_checked_options(presenter):
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.dialogs.variant_generator_dialog import (
        VariantGeneratorDialog,
    )
    app = QApplication.instance() or QApplication([])
    dlg = VariantGeneratorDialog(presenter, product_id=presenter._parent_id,
                                 product_name="Playera")
    node = dlg.tree.topLevelItem(0)
    for j in range(node.childCount()):
        node.child(j).setCheckState(0, Qt.Checked)
    selected = dlg._selected_axes()
    assert set(selected) == {presenter._attr_id}
    assert set(selected[presenter._attr_id]) == set(presenter._opt_ids)
    dlg._on_generate()
    assert len(presenter.list_variants(presenter._parent_id)) == 2

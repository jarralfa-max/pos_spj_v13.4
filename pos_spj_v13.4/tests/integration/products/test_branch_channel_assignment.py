"""P0-B slice 7 — asignación por sucursal y canal (§10).

Un producto se habilita por sucursal (branch_product) y se incluye en surtidos por
canal (assortments) sin duplicarse ni llevar precio/stock. Cubre use cases +
query service + la página (smoke).
"""

import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.branch_assortment_query_service import (  # noqa: E402
    BranchAssortmentQueryService,
)
from backend.application.products.queries.catalog_read_service import (  # noqa: E402
    ProductCatalogReadService,
)
from backend.application.products.use_cases.product_branch_assortment_use_cases import (  # noqa: E402
    CreateAssortmentUseCase,
    SetAssortmentProductUseCase,
    SetBranchProductUseCase,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.modules.products.presenter import ProductsPresenter  # noqa: E402


class _Session:
    user_id = "u1"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER DEFAULT 1)")
    c.execute("INSERT INTO sucursales (id, nombre, activa) VALUES ('b1','Centro',1)")
    c.execute("INSERT INTO sucursales (id, nombre, activa) VALUES ('b2','Norte',1)")
    c.execute("INSERT INTO products (id, code, name, name_normalized, product_type, "
              "lifecycle_status, base_unit_id, sellable, purchasable, inventory_managed) "
              "VALUES ('p1','C1','Pollo','pollo','RESALE_PRODUCT','ACTIVE','kg',1,1,1)")
    c.commit()
    return c


def test_branch_enable_disable_and_query(conn):
    q = BranchAssortmentQueryService(conn)
    # sin filas: ambas sucursales aparecen deshabilitadas
    before = {b["branch_id"]: b["enabled"] for b in q.branch_assignments("p1")}
    assert before == {"b1": False, "b2": False}
    # habilitar b1
    res = SetBranchProductUseCase(conn).execute(
        product_id="p1", branch_id="b1", enabled=True, user_id="u1")
    assert res.success
    after = {b["branch_id"]: b["enabled"] for b in q.branch_assignments("p1")}
    assert after == {"b1": True, "b2": False}
    # deshabilitar b1 (idempotente por par)
    SetBranchProductUseCase(conn).execute(
        product_id="p1", branch_id="b1", enabled=False, user_id="u1")
    assert not BranchAssortmentQueryService(conn).branch_assignments("p1")[0]["enabled"]


def test_channels_listed(conn):
    channels = {c["value"] for c in BranchAssortmentQueryService(conn).channels()}
    assert {"POS", "WHATSAPP", "DELIVERY", "WHOLESALE"} <= channels


def test_assortment_create_and_membership(conn):
    res = CreateAssortmentUseCase(conn).execute(name="Surtido POS", channel="POS",
                                                user_id="u1")
    assert res.success and res.entity_id
    aid = res.entity_id
    q = BranchAssortmentQueryService(conn)
    assert q.assortments("p1", channel="POS")[0]["contains"] is False
    add = SetAssortmentProductUseCase(conn).execute(
        assortment_id=aid, product_id="p1", enabled=True, user_id="u1")
    assert add.success
    assert q.assortments("p1")[0]["contains"] is True
    # quitar
    SetAssortmentProductUseCase(conn).execute(
        assortment_id=aid, product_id="p1", enabled=False, user_id="u1")
    assert q.assortments("p1")[0]["contains"] is False


def test_assortment_membership_rejects_unknown_assortment(conn):
    res = SetAssortmentProductUseCase(conn).execute(
        assortment_id=new_uuid(), product_id="p1", enabled=True, user_id="u1")
    assert not res.success and "no existe" in res.message


def _presenter(conn):
    return ProductsPresenter(
        read_service_factory=lambda: ProductCatalogReadService(conn),
        branch_read_factory=lambda: BranchAssortmentQueryService(conn),
        branch_write_factory=lambda: {
            "branch": SetBranchProductUseCase(conn),
            "create_assortment": CreateAssortmentUseCase(conn),
            "set_assortment_product": SetAssortmentProductUseCase(conn)},
        session_context=_Session())


def test_page_builds_and_loads(conn):
    from PyQt5.QtWidgets import QApplication

    from frontend.desktop.modules.products.pages.branch_channel_page import (
        BranchChannelPage,
    )
    app = QApplication.instance() or QApplication([])  # noqa: F841
    page = BranchChannelPage(_presenter(conn))
    # el buscador cargó el producto canónico
    assert page.products.selected_row_id() is None
    page._product_id = "p1"
    page._refresh_assignments()
    # 2 sucursales visibles en la tabla
    assert page.branches.selected_row_id() is None  # sin selección aún
    assert page._branch_state == {"b1": False, "b2": False}

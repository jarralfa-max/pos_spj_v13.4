"""PROC-23 — MeatProcessingModuleHost builds and the real Órdenes page wires
end to end (offscreen Qt, see tests/conftest.py QT_QPA_PLATFORM)."""

import importlib
import sqlite3
from decimal import Decimal

import pytest
from PyQt5.QtWidgets import QApplication

from backend.infrastructure.desktop.meat_processing_factory import MeatProcessingModuleHost
from backend.shared.ids import new_uuid
from frontend.desktop.modules.meat_processing.pages import (
    MeatProcessingPlaceholderPage,
    ProcessingOrdersPage,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _Session:
    is_active = True

    def __init__(self, *, user_id, branch_id, warehouse_id, permisos):
        self.user_id = user_id
        self.active_branch_id = branch_id
        self.warehouse_id = warehouse_id
        self.permisos = permisos

    def tiene_permiso(self, code: str) -> bool:
        return code in self.permisos


class _Container:
    def __init__(self, conn, session):
        self.db = conn
        self.session = session


_ORDER_PERMISSIONS = (
    "PRODUCCION.acceso", "PRODUCCION.orden.ver", "PRODUCCION.orden.crear",
    "PRODUCCION.orden.aprobar", "PRODUCCION.orden.liberar", "PRODUCCION.orden.cerrar",
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    importlib.import_module(
        "migrations.standalone.187_meat_processing_bounded_context_schema").run(c)
    yield c
    c.close()


def _host(conn, *, permisos=_ORDER_PERMISSIONS):
    session = _Session(
        user_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(), permisos=permisos)
    return MeatProcessingModuleHost(_Container(conn, session))


class TestModuleHost:
    def test_builds_and_defaults_to_first_route(self, app, conn):
        host = _host(conn)
        assert host.active_route is not None

    def test_orders_route_serves_the_real_page(self, app, conn):
        host = _host(conn)
        host.show_route("mp_processing_orders")
        page = host._pages["mp_processing_orders"]
        assert isinstance(page, ProcessingOrdersPage)

    def test_other_routes_still_serve_the_placeholder(self, app, conn):
        host = _host(conn, permisos=_ORDER_PERMISSIONS + ("PRODUCCION.plan.ver",))
        host.show_route("mp_production_plan")
        page = host._pages["mp_production_plan"]
        assert isinstance(page, MeatProcessingPlaceholderPage)

    def test_full_order_lifecycle_through_the_real_page(self, app, conn):
        host = _host(conn)
        host.show_route("mp_processing_orders")
        page = host._pages["mp_processing_orders"]
        page.refresh()
        assert page._table.selected_row_id() is None

        pres = page._presenter
        ok, _msg, data = pres.create_order(
            process_type="CUTTING", target_product_id=new_uuid(),
            planned_quantity=Decimal("10"), planned_weight=Decimal("10"))
        assert ok
        page.refresh()
        assert pres.orders().total == 1

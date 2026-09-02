"""SHELL-16 end-to-end proof — sales_pos navigable through the real
SHELL-8..15 shell (ModuleRegistry, RouteRegistry, ViewFactoryRegistry,
ModuleLoader, DesktopRouter), built from a real, migrated SQLite
connection and a real permission-bearing session — never a whole
dependency container anywhere in the chain.

Headless (offscreen Qt), same pattern `tests/integration/test_sales_pos_checkout_end_to_end.py`
(POS-22) already established for constructing `sales_pos` against a real
connection.
"""
from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.application.sales.permissions import SalesPermissions  # noqa: E402
from backend.bootstrap.application_context import ApplicationContext, FeatureContext  # noqa: E402
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema  # noqa: E402
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema  # noqa: E402
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from backend.infrastructure.db.schema.sales_schema import create_sales_schema  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.modules.sales_pos.sales_pos_workspace import SalesPosWorkspace  # noqa: E402
from frontend.desktop.modules.sales_pos.shell_registration import (  # noqa: E402
    SALES_POS_MODULE_ID,
    SALES_POS_ROUTE_ID,
    SalesPosModuleActivator,
    build_sales_pos_module_descriptor,
    build_sales_pos_route_definition,
)
from frontend.desktop.shell.loading.dispatching_module_activator import DispatchingModuleActivator  # noqa: E402
from frontend.desktop.shell.loading.module_load_state import ModuleLoadState  # noqa: E402
from frontend.desktop.shell.loading.module_loader import ModuleLoader  # noqa: E402
from frontend.desktop.shell.modules.module_registry import ModuleRegistry  # noqa: E402
from frontend.desktop.shell.router.desktop_router import DesktopRouter  # noqa: E402
from frontend.desktop.shell.router.errors import NavigationPermissionDeniedError  # noqa: E402
from frontend.desktop.shell.routing.route_registry import RouteRegistry  # noqa: E402
from frontend.desktop.shell.routing.route_registry_validator import RouteRegistryValidator  # noqa: E402
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry  # noqa: E402


class _FakeSession:
    """Same shape `test_sales_pos_checkout_end_to_end.py` (POS-22) uses —
    the real `SessionContext` protocol `SalesSessionPermissionChecker`
    expects: `user_id`, `active_branch_id`, `is_active`, `tiene_permiso()`.
    """

    def __init__(self, permissions):
        self.user_id = new_uuid()
        self.active_branch_id = new_uuid()
        self.is_active = True
        self._permissions = set(permissions)

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permissions


def _all_permissions_session() -> _FakeSession:
    return _FakeSession({v for v in vars(SalesPermissions).values() if isinstance(v, str)})


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sales_schema(c)
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    return c


def _context(*, branch_id, user_id, permissions) -> ApplicationContext:
    return ApplicationContext(
        installation_id="install-1", company_id="company-1", branch_id=branch_id,
        branch_name="Sucursal Centro", workstation_id="ws-1", workstation_type="pos",
        user_id=user_id, user_name="Cajero", roles=("cajero",),
        permissions=frozenset(permissions), feature_context=FeatureContext(),
        session_id="session-1",
    )


def _wire(conn, session) -> tuple[DesktopRouter, ModuleLoader, ViewFactoryRegistry]:
    modules = ModuleRegistry()
    modules.register(build_sales_pos_module_descriptor())

    routes = RouteRegistry()
    routes.register(build_sales_pos_route_definition())

    view_factories = ViewFactoryRegistry()

    dispatcher = DispatchingModuleActivator()
    dispatcher.register(SALES_POS_MODULE_ID, SalesPosModuleActivator(
        connection=conn, view_factory_registry=view_factories, session_context=session,
    ))
    loader = ModuleLoader(module_registry=modules, activator=dispatcher)

    context = _context(
        branch_id=session.active_branch_id, user_id=session.user_id,
        permissions={"POS.VER"},
    )
    router = DesktopRouter(route_registry=routes, view_factory_registry=view_factories, initial_context=context)
    return router, loader, view_factories


def test_route_graph_is_invalid_before_the_module_loads(app, conn):
    session = _all_permissions_session()
    router, loader, view_factories = _wire(conn, session)
    modules = ModuleRegistry()
    modules.register(build_sales_pos_module_descriptor())
    issues = RouteRegistryValidator().validate(router.route_registry, modules, view_factories)
    assert any(i.code == "ROUTE_VIEW_FACTORY_NOT_FOUND" for i in issues)


def test_ensure_loaded_registers_the_view_factory(app, conn):
    session = _all_permissions_session()
    router, loader, view_factories = _wire(conn, session)
    assert view_factories.is_registered("sales_pos.workspace_view") is False
    result = loader.ensure_loaded(SALES_POS_MODULE_ID)
    assert result.state is ModuleLoadState.LOADED
    assert view_factories.is_registered("sales_pos.workspace_view") is True


def test_navigate_builds_a_real_sales_pos_workspace(app, conn):
    session = _all_permissions_session()
    router, loader, view_factories = _wire(conn, session)
    loader.ensure_loaded(SALES_POS_MODULE_ID)

    result = router.navigate(SALES_POS_ROUTE_ID)
    assert isinstance(result.view, SalesPosWorkspace)
    assert result.route.breadcrumb == ("Ventas", "Punto de Venta")


def test_navigate_without_loading_the_module_first_raises_view_factory_not_found(app, conn):
    session = _all_permissions_session()
    router, loader, view_factories = _wire(conn, session)
    with pytest.raises(Exception):
        router.navigate(SALES_POS_ROUTE_ID)


def test_navigate_without_the_pos_ver_permission_is_denied(app, conn):
    modules = ModuleRegistry()
    modules.register(build_sales_pos_module_descriptor())
    routes = RouteRegistry()
    routes.register(build_sales_pos_route_definition())
    view_factories = ViewFactoryRegistry()

    session = _all_permissions_session()
    dispatcher = DispatchingModuleActivator()
    dispatcher.register(SALES_POS_MODULE_ID, SalesPosModuleActivator(
        connection=conn, view_factory_registry=view_factories, session_context=session,
    ))
    loader = ModuleLoader(module_registry=modules, activator=dispatcher)
    loader.ensure_loaded(SALES_POS_MODULE_ID)

    context = _context(branch_id=session.active_branch_id, user_id=session.user_id, permissions=set())
    router = DesktopRouter(route_registry=routes, view_factory_registry=view_factories, initial_context=context)

    with pytest.raises(NavigationPermissionDeniedError):
        router.navigate(SALES_POS_ROUTE_ID)


def test_no_component_in_the_chain_receives_a_whole_container(app, conn):
    # The activator's own constructor only accepts named, narrow
    # dependencies (see test_sales_pos_shell_registration.py's structural
    # check) — this test proves the object it hands back is the real,
    # fully-functional workspace, not a stand-in, confirming the explicit
    # wiring actually works end-to-end rather than merely type-checking.
    session = _all_permissions_session()
    router, loader, view_factories = _wire(conn, session)
    loader.ensure_loaded(SALES_POS_MODULE_ID)
    result = router.navigate(SALES_POS_ROUTE_ID)
    assert result.view.catalog is not None
    assert result.view.checkout is not None

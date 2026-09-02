"""SHELL-16 end-to-end proof — inventory navigable through the real
SHELL-8..15 shell (ModuleRegistry, RouteRegistry, ViewFactoryRegistry,
ModuleLoader, DesktopRouter), built from a real, migrated SQLite
connection — never a whole dependency container anywhere in the chain.

Headless (offscreen Qt). Schema setup mirrors
`tests/integration/inventory/test_inventory_enterprise_session_wiring.py`.
"""
from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.bootstrap.application_context import ApplicationContext, FeatureContext  # noqa: E402
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema  # noqa: E402
from frontend.desktop.modules.inventory.inventory_view import InventoryView  # noqa: E402
from frontend.desktop.modules.inventory.shell_registration import (  # noqa: E402
    INVENTORY_MODULE_ID,
    INVENTORY_ROUTE_ID,
    InventoryModuleActivator,
    build_inventory_module_descriptor,
    build_inventory_route_definition,
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


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    return c


def _context(*, permissions) -> ApplicationContext:
    return ApplicationContext(
        installation_id="install-1", company_id="company-1", branch_id="branch-1",
        branch_name="Sucursal Centro", workstation_id="ws-1", workstation_type="pos",
        user_id="user-1", user_name="Almacenista", roles=("cajero",),
        permissions=frozenset(permissions), feature_context=FeatureContext(),
        session_id="session-1",
    )


def _wire(conn, *, permissions) -> tuple[DesktopRouter, ModuleLoader, ViewFactoryRegistry]:
    modules = ModuleRegistry()
    modules.register(build_inventory_module_descriptor())

    routes = RouteRegistry()
    routes.register(build_inventory_route_definition())

    view_factories = ViewFactoryRegistry()

    dispatcher = DispatchingModuleActivator()
    dispatcher.register(INVENTORY_MODULE_ID, InventoryModuleActivator(
        connection=conn, view_factory_registry=view_factories,
    ))
    loader = ModuleLoader(module_registry=modules, activator=dispatcher)

    router = DesktopRouter(
        route_registry=routes, view_factory_registry=view_factories,
        initial_context=_context(permissions=permissions),
    )
    return router, loader, view_factories


def test_route_graph_is_invalid_before_the_module_loads(app, conn):
    router, loader, view_factories = _wire(conn, permissions={"INVENTARIO.VER"})
    modules = ModuleRegistry()
    modules.register(build_inventory_module_descriptor())
    issues = RouteRegistryValidator().validate(router.route_registry, modules, view_factories)
    assert any(i.code == "ROUTE_VIEW_FACTORY_NOT_FOUND" for i in issues)


def test_ensure_loaded_registers_the_view_factory(app, conn):
    router, loader, view_factories = _wire(conn, permissions={"INVENTARIO.VER"})
    assert view_factories.is_registered("inventory.workspace_view") is False
    result = loader.ensure_loaded(INVENTORY_MODULE_ID)
    assert result.state is ModuleLoadState.LOADED
    assert view_factories.is_registered("inventory.workspace_view") is True


def test_navigate_builds_a_real_inventory_view(app, conn):
    router, loader, view_factories = _wire(conn, permissions={"INVENTARIO.VER"})
    loader.ensure_loaded(INVENTORY_MODULE_ID)

    result = router.navigate(INVENTORY_ROUTE_ID)
    assert isinstance(result.view, InventoryView)
    assert result.route.breadcrumb == ("Inventario",)


def test_navigate_without_the_required_permission_is_denied(app, conn):
    router, loader, view_factories = _wire(conn, permissions=set())
    loader.ensure_loaded(INVENTORY_MODULE_ID)
    with pytest.raises(NavigationPermissionDeniedError):
        router.navigate(INVENTORY_ROUTE_ID)


def test_navigated_workspace_has_no_session_starts_with_empty_scope(app, conn):
    """Same fail-closed invariant the extraction preserved (see
    composition.py's docstring): no session_context passed through the
    shell means the presenter degrades to empty scope, never a fabricated
    identity."""
    router, loader, view_factories = _wire(conn, permissions={"INVENTARIO.VER"})
    loader.ensure_loaded(INVENTORY_MODULE_ID)
    result = router.navigate(INVENTORY_ROUTE_ID)
    presenter = result.view._presenter
    assert presenter.default_branch() == ""
    assert presenter.default_warehouse() == ""

"""SHELL-16 end-to-end proof — transfers navigable through the real
SHELL-8..15 shell (ModuleRegistry, RouteRegistry, ViewFactoryRegistry,
ModuleLoader, DesktopRouter), built from a real, migrated SQLite
connection — never a whole dependency container anywhere in the chain.

Headless (offscreen Qt). Schema/seed setup mirrors
`tests/integration/transfers/test_create_transfer_request_e2e.py`, which
documents itself as exercising "the exact path `TransfersModuleHost`
wires in production" — this test proves the same production composition
is reachable through the new shell instead.
"""
from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.bootstrap.application_context import ApplicationContext, FeatureContext  # noqa: E402
from backend.infrastructure.db.schema.transfers_schema import create_transfers_schema  # noqa: E402
from frontend.desktop.modules.transfers.shell_registration import (  # noqa: E402
    TRANSFERS_MODULE_ID,
    TRANSFERS_ROUTE_ID,
    TransfersModuleActivator,
    build_transfers_module_descriptor,
    build_transfers_route_definition,
)
from frontend.desktop.modules.transfers.transfers_view import TransfersView  # noqa: E402
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
    user_id = "u1"
    is_active = True
    active_branch_id = "b1"

    def tiene_permiso(self, code):
        return code in {"TRANSFERENCIAS.ver", "TRANSFERENCIAS.crear"}


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    create_transfers_schema(c)
    c.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    c.execute("INSERT INTO sucursales VALUES ('b1', 'Matriz', 1), ('b2', 'Sucursal Centro', 1)")
    c.execute("CREATE TABLE products (id TEXT PRIMARY KEY, base_unit_id TEXT)")
    c.execute("INSERT INTO products VALUES ('p1', 'unit-kg')")
    c.commit()
    return c


def _context(*, permissions) -> ApplicationContext:
    return ApplicationContext(
        installation_id="install-1", company_id="company-1", branch_id="b1",
        branch_name="Matriz", workstation_id="ws-1", workstation_type="pos",
        user_id="u1", user_name="Almacenista", roles=("almacenista",),
        permissions=frozenset(permissions), feature_context=FeatureContext(),
        session_id="session-1",
    )


def _wire(conn, *, permissions, session_context=None):
    modules = ModuleRegistry()
    modules.register(build_transfers_module_descriptor())

    routes = RouteRegistry()
    routes.register(build_transfers_route_definition())

    view_factories = ViewFactoryRegistry()

    dispatcher = DispatchingModuleActivator()
    dispatcher.register(TRANSFERS_MODULE_ID, TransfersModuleActivator(
        connection=conn, view_factory_registry=view_factories, session_context=session_context,
    ))
    loader = ModuleLoader(module_registry=modules, activator=dispatcher)

    router = DesktopRouter(
        route_registry=routes, view_factory_registry=view_factories,
        initial_context=_context(permissions=permissions),
    )
    return router, loader, view_factories


def test_route_graph_is_invalid_before_the_module_loads(app, conn):
    router, loader, view_factories = _wire(conn, permissions={"TRANSFERENCIAS.VER"}, session_context=_FakeSession())
    modules = ModuleRegistry()
    modules.register(build_transfers_module_descriptor())
    issues = RouteRegistryValidator().validate(router.route_registry, modules, view_factories)
    assert any(i.code == "ROUTE_VIEW_FACTORY_NOT_FOUND" for i in issues)


def test_ensure_loaded_registers_the_view_factory(app, conn):
    router, loader, view_factories = _wire(conn, permissions={"TRANSFERENCIAS.VER"}, session_context=_FakeSession())
    assert view_factories.is_registered("transfers.workspace_view") is False
    result = loader.ensure_loaded(TRANSFERS_MODULE_ID)
    assert result.state is ModuleLoadState.LOADED
    assert view_factories.is_registered("transfers.workspace_view") is True


def test_navigate_builds_a_real_transfers_view(app, conn):
    router, loader, view_factories = _wire(conn, permissions={"TRANSFERENCIAS.VER"}, session_context=_FakeSession())
    loader.ensure_loaded(TRANSFERS_MODULE_ID)

    result = router.navigate(TRANSFERS_ROUTE_ID)
    assert isinstance(result.view, TransfersView)
    assert result.route.breadcrumb == ("Transferencias",)


def test_navigate_without_the_required_permission_is_denied(app, conn):
    router, loader, view_factories = _wire(conn, permissions=set(), session_context=_FakeSession())
    loader.ensure_loaded(TRANSFERS_MODULE_ID)
    with pytest.raises(NavigationPermissionDeniedError):
        router.navigate(TRANSFERS_ROUTE_ID)

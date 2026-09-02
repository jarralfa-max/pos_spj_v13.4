"""SHELL-16 end-to-end proof — purchasing navigable through the real
SHELL-8..15 shell (ModuleRegistry, RouteRegistry, ViewFactoryRegistry,
ModuleLoader, DesktopRouter), built from a real, migrated SQLite
connection — never a whole dependency container anywhere in the chain.

Headless (offscreen Qt). Schema setup mirrors
`tests/integration/procurement/conftest.py::proc_conn`.
"""
from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.bootstrap.application_context import ApplicationContext, FeatureContext  # noqa: E402
from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema  # noqa: E402
from frontend.desktop.modules.purchasing.enterprise_view import EnterprisePurchasingView  # noqa: E402
from frontend.desktop.modules.purchasing.shell_registration import (  # noqa: E402
    PURCHASING_MODULE_ID,
    PURCHASING_ROUTE_ID,
    PurchasingModuleActivator,
    build_purchasing_module_descriptor,
    build_purchasing_route_definition,
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
    """A session with an active branch — `EnterprisePurchasingPresenter.default_branch()`
    (called eagerly while building the view's warehouse filter) raises
    `PermissionError` without one, same as production."""

    def __init__(self, branch_id="branch-1"):
        self.active_branch_id = branch_id
        self.user_id = "user-1"

    def tiene_permiso(self, _code):
        return True


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    create_procurement_schema(c)
    return c


def _context(*, permissions) -> ApplicationContext:
    return ApplicationContext(
        installation_id="install-1", company_id="company-1", branch_id="branch-1",
        branch_name="Sucursal Centro", workstation_id="ws-1", workstation_type="pos",
        user_id="user-1", user_name="Comprador", roles=("cajero",),
        permissions=frozenset(permissions), feature_context=FeatureContext(),
        session_id="session-1",
    )


def _wire(conn, *, permissions, session_context=None):
    modules = ModuleRegistry()
    modules.register(build_purchasing_module_descriptor())

    routes = RouteRegistry()
    routes.register(build_purchasing_route_definition())

    view_factories = ViewFactoryRegistry()

    dispatcher = DispatchingModuleActivator()
    dispatcher.register(PURCHASING_MODULE_ID, PurchasingModuleActivator(
        connection=conn, view_factory_registry=view_factories, session_context=session_context,
    ))
    loader = ModuleLoader(module_registry=modules, activator=dispatcher)

    router = DesktopRouter(
        route_registry=routes, view_factory_registry=view_factories,
        initial_context=_context(permissions=permissions),
    )
    return router, loader, view_factories


def test_route_graph_is_invalid_before_the_module_loads(app, conn):
    router, loader, view_factories = _wire(conn, permissions={"COMPRAS.VER"}, session_context=_FakeSession())
    modules = ModuleRegistry()
    modules.register(build_purchasing_module_descriptor())
    issues = RouteRegistryValidator().validate(router.route_registry, modules, view_factories)
    assert any(i.code == "ROUTE_VIEW_FACTORY_NOT_FOUND" for i in issues)


def test_ensure_loaded_registers_the_view_factory(app, conn):
    router, loader, view_factories = _wire(conn, permissions={"COMPRAS.VER"}, session_context=_FakeSession())
    assert view_factories.is_registered("purchasing.workspace_view") is False
    result = loader.ensure_loaded(PURCHASING_MODULE_ID)
    assert result.state is ModuleLoadState.LOADED
    assert view_factories.is_registered("purchasing.workspace_view") is True


def test_navigate_builds_a_real_purchasing_view(app, conn):
    router, loader, view_factories = _wire(conn, permissions={"COMPRAS.VER"}, session_context=_FakeSession())
    loader.ensure_loaded(PURCHASING_MODULE_ID)

    result = router.navigate(PURCHASING_ROUTE_ID)
    assert isinstance(result.view, EnterprisePurchasingView)
    assert result.route.breadcrumb == ("Compras",)


def test_navigate_without_the_required_permission_is_denied(app, conn):
    router, loader, view_factories = _wire(conn, permissions=set(), session_context=_FakeSession())
    loader.ensure_loaded(PURCHASING_MODULE_ID)
    with pytest.raises(NavigationPermissionDeniedError):
        router.navigate(PURCHASING_ROUTE_ID)

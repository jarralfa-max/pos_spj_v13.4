"""SHELL-16 end-to-end proof — products navigable through the real
SHELL-8..15 shell (ModuleRegistry, RouteRegistry, ViewFactoryRegistry,
ModuleLoader, DesktopRouter), built from a real, migrated SQLite
connection — never a whole dependency container anywhere in the chain.

Headless (offscreen Qt). Schema setup mirrors
`tests/integration/products/test_products_enterprise_host.py`.
"""
from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.bootstrap.application_context import ApplicationContext, FeatureContext  # noqa: E402
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402
from frontend.desktop.modules.products.products_view import ProductsView  # noqa: E402
from frontend.desktop.modules.products.shell_registration import (  # noqa: E402
    PRODUCTS_MODULE_ID,
    PRODUCTS_ROUTE_ID,
    ProductsModuleActivator,
    build_products_module_descriptor,
    build_products_route_definition,
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


class _FakeLiveSession:
    """Same minimal double `test_products_enterprise_host.py` uses: only
    exposes `user_id` (§21.2)."""

    def __init__(self, user_id):
        self.user_id = user_id

    def tiene_permiso(self, _code):
        return True


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.commit()
    return c


def _context(*, permissions) -> ApplicationContext:
    return ApplicationContext(
        installation_id="install-1", company_id="company-1", branch_id="branch-1",
        branch_name="Sucursal Centro", workstation_id="ws-1", workstation_type="pos",
        user_id="user-1", user_name="Catalogador", roles=("cajero",),
        permissions=frozenset(permissions), feature_context=FeatureContext(),
        session_id="session-1",
    )


def _wire(conn, *, permissions, live_session=None, branch_id_fallback=None):
    modules = ModuleRegistry()
    modules.register(build_products_module_descriptor())

    routes = RouteRegistry()
    routes.register(build_products_route_definition())

    view_factories = ViewFactoryRegistry()

    dispatcher = DispatchingModuleActivator()
    dispatcher.register(PRODUCTS_MODULE_ID, ProductsModuleActivator(
        connection=conn, view_factory_registry=view_factories,
        live_session=live_session, branch_id_fallback=branch_id_fallback,
    ))
    loader = ModuleLoader(module_registry=modules, activator=dispatcher)

    router = DesktopRouter(
        route_registry=routes, view_factory_registry=view_factories,
        initial_context=_context(permissions=permissions),
    )
    return router, loader, view_factories


def test_route_graph_is_invalid_before_the_module_loads(app, conn):
    router, loader, view_factories = _wire(conn, permissions={"PRODUCTOS.VER"})
    modules = ModuleRegistry()
    modules.register(build_products_module_descriptor())
    issues = RouteRegistryValidator().validate(router.route_registry, modules, view_factories)
    assert any(i.code == "ROUTE_VIEW_FACTORY_NOT_FOUND" for i in issues)


def test_ensure_loaded_registers_the_view_factory(app, conn):
    router, loader, view_factories = _wire(conn, permissions={"PRODUCTOS.VER"})
    assert view_factories.is_registered("products.workspace_view") is False
    result = loader.ensure_loaded(PRODUCTS_MODULE_ID)
    assert result.state is ModuleLoadState.LOADED
    assert view_factories.is_registered("products.workspace_view") is True


def test_navigate_builds_a_real_products_view(app, conn):
    router, loader, view_factories = _wire(conn, permissions={"PRODUCTOS.VER"})
    loader.ensure_loaded(PRODUCTS_MODULE_ID)

    result = router.navigate(PRODUCTS_ROUTE_ID)
    assert isinstance(result.view, ProductsView)
    assert result.route.breadcrumb == ("Productos",)
    assert result.view.nav.count() == 7


def test_navigate_without_the_required_permission_is_denied(app, conn):
    router, loader, view_factories = _wire(conn, permissions=set())
    loader.ensure_loaded(PRODUCTS_MODULE_ID)
    with pytest.raises(NavigationPermissionDeniedError):
        router.navigate(PRODUCTS_ROUTE_ID)


def test_no_session_degrades_to_empty_identity_not_fabricated(app, conn):
    router, loader, view_factories = _wire(conn, permissions={"PRODUCTOS.VER"})
    loader.ensure_loaded(PRODUCTS_MODULE_ID)
    result = router.navigate(PRODUCTS_ROUTE_ID)
    session_context = result.view._presenter._session
    assert session_context.user_id is None
    assert session_context.branch_id is None


def test_branch_id_fallback_is_used_when_no_live_branch(app, conn):
    router, loader, view_factories = _wire(
        conn, permissions={"PRODUCTOS.VER"}, live_session=_FakeLiveSession("user-abc"),
        branch_id_fallback="b1",
    )
    loader.ensure_loaded(PRODUCTS_MODULE_ID)
    result = router.navigate(PRODUCTS_ROUTE_ID)
    session_context = result.view._presenter._session
    assert session_context.user_id == "user-abc"
    assert session_context.branch_id == "b1"


def test_identity_resolves_live_not_at_activation_time(app, conn):
    """Same regression the original module protects (`test_identity_resolves_live_not_at_construction_time`):
    mutating the live session AFTER the view was built must be reflected —
    the wrapper never freezes a snapshot."""
    live_session = _FakeLiveSession(user_id=None)
    router, loader, view_factories = _wire(
        conn, permissions={"PRODUCTOS.VER"}, live_session=live_session,
    )
    loader.ensure_loaded(PRODUCTS_MODULE_ID)
    result = router.navigate(PRODUCTS_ROUTE_ID)
    session_context = result.view._presenter._session
    assert session_context.user_id is None

    live_session.user_id = "user-post-login"
    assert session_context.user_id == "user-post-login"

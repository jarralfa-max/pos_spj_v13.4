"""SHELL-16 end-to-end proof — hr navigable through the real SHELL-8..15
shell (ModuleRegistry, RouteRegistry, ViewFactoryRegistry, ModuleLoader,
DesktopRouter), built from a real SQLite connection (schema self-bootstrapped
by `build_hr_presenter`, same as `tests/integration/hr/conftest.py::hr_conn`)
— never a whole dependency container anywhere in the chain.

Headless (offscreen Qt).
"""
from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.bootstrap.application_context import ApplicationContext, FeatureContext  # noqa: E402
from frontend.desktop.modules.hr.hr_view import HRView  # noqa: E402
from frontend.desktop.modules.hr.shell_registration import (  # noqa: E402
    HR_MODULE_ID,
    HR_ROUTE_ID,
    HRModuleActivator,
    build_hr_module_descriptor,
    build_hr_route_definition,
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
    c.execute("PRAGMA foreign_keys = ON")
    return c


def _context(*, permissions) -> ApplicationContext:
    return ApplicationContext(
        installation_id="install-1", company_id="company-1", branch_id="branch-1",
        branch_name="Sucursal Centro", workstation_id="ws-1", workstation_type="pos",
        user_id="user-1", user_name="RRHH", roles=("cajero",),
        permissions=frozenset(permissions), feature_context=FeatureContext(),
        session_id="session-1",
    )


def _wire(conn, *, permissions) -> tuple[DesktopRouter, ModuleLoader, ViewFactoryRegistry]:
    modules = ModuleRegistry()
    modules.register(build_hr_module_descriptor())

    routes = RouteRegistry()
    routes.register(build_hr_route_definition())

    view_factories = ViewFactoryRegistry()

    dispatcher = DispatchingModuleActivator()
    dispatcher.register(HR_MODULE_ID, HRModuleActivator(
        connection=conn, view_factory_registry=view_factories,
    ))
    loader = ModuleLoader(module_registry=modules, activator=dispatcher)

    router = DesktopRouter(
        route_registry=routes, view_factory_registry=view_factories,
        initial_context=_context(permissions=permissions),
    )
    return router, loader, view_factories


def test_route_graph_is_invalid_before_the_module_loads(app, conn):
    router, loader, view_factories = _wire(conn, permissions={"RRHH.VER"})
    modules = ModuleRegistry()
    modules.register(build_hr_module_descriptor())
    issues = RouteRegistryValidator().validate(router.route_registry, modules, view_factories)
    assert any(i.code == "ROUTE_VIEW_FACTORY_NOT_FOUND" for i in issues)


def test_ensure_loaded_registers_the_view_factory(app, conn):
    router, loader, view_factories = _wire(conn, permissions={"RRHH.VER"})
    assert view_factories.is_registered("hr.workspace_view") is False
    result = loader.ensure_loaded(HR_MODULE_ID)
    assert result.state is ModuleLoadState.LOADED
    assert view_factories.is_registered("hr.workspace_view") is True


def test_navigate_builds_a_real_hr_view(app, conn):
    router, loader, view_factories = _wire(conn, permissions={"RRHH.VER"})
    loader.ensure_loaded(HR_MODULE_ID)

    result = router.navigate(HR_ROUTE_ID)
    assert isinstance(result.view, HRView)
    assert result.route.breadcrumb == ("Recursos Humanos",)


def test_navigate_without_the_required_permission_is_denied(app, conn):
    router, loader, view_factories = _wire(conn, permissions=set())
    loader.ensure_loaded(HR_MODULE_ID)
    with pytest.raises(NavigationPermissionDeniedError):
        router.navigate(HR_ROUTE_ID)

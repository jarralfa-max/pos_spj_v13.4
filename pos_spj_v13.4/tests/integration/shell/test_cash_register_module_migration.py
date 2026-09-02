"""SHELL-16 end-to-end proof — cash_register navigable through the real
SHELL-8..15 shell (ModuleRegistry, RouteRegistry, ViewFactoryRegistry,
ModuleLoader, DesktopRouter), built from a real, migrated SQLite
connection — never the real application container anywhere in the chain
(only a minimal, purpose-built stand-in — see `shell_registration.py`'s
own docstring for why this module needed a different strategy than
modules 1-7).

Headless (offscreen Qt). Schema/seed setup mirrors
`tests/integration/cash_register/test_cash_register_factory_active_context.py`.

A real cash register/drawer/terminal must be seeded for the branch —
constructing the workspace against a branch with none of those crashes the
whole process (a segfault, reproduced independently against the
completely unmodified, pre-existing `create_cash_register_view()` with no
involvement from this migration's own code — a latent bug in the existing
widget construction path that no prior test exercised, since none built
the full widget end-to-end before this phase). Out of scope to fix here;
flagged to the user, not silently worked around.
"""
from __future__ import annotations

import importlib
import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.bootstrap.application_context import ApplicationContext, FeatureContext  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.modules.cash_register.cash_register_workspace import CashRegisterWorkspace  # noqa: E402
from frontend.desktop.modules.cash_register.shell_registration import (  # noqa: E402
    CASH_REGISTER_MODULE_ID,
    CASH_REGISTER_ROUTE_ID,
    CashRegisterModuleActivator,
    build_cash_register_module_descriptor,
    build_cash_register_route_definition,
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

_NOW = "2026-08-13T12:00:00+00:00"


class _FakeSession:
    is_active = True

    def __init__(self, *, user_id, branch_id):
        self.user_id = user_id
        self.active_branch_id = branch_id

    def tiene_permiso(self, _code):
        return True


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def branch_id():
    return new_uuid()


@pytest.fixture
def conn(branch_id):
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    importlib.import_module("migrations.standalone.176_cash_register_configuration_schema").run(c)
    importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(c)

    register_id, drawer_id, terminal_id = new_uuid(), new_uuid(), new_uuid()
    c.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
              (register_id, branch_id, "Caja principal", "ACTIVE", None, _NOW, _NOW))
    c.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
              (drawer_id, branch_id, register_id, "Cajon principal", "ACTIVE", _NOW, _NOW))
    c.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
              (terminal_id, branch_id, register_id, "Terminal principal", "ACTIVE", _NOW, _NOW))
    c.commit()
    return c


def _context(*, branch_id, permissions) -> ApplicationContext:
    return ApplicationContext(
        installation_id="install-1", company_id="company-1", branch_id=branch_id,
        branch_name="Sucursal Centro", workstation_id="ws-1", workstation_type="pos",
        user_id="user-1", user_name="Cajero", roles=("cajero",),
        permissions=frozenset(permissions), feature_context=FeatureContext(),
        session_id="session-1",
    )


def _wire(conn, branch_id, *, permissions, session_context=None):
    modules = ModuleRegistry()
    modules.register(build_cash_register_module_descriptor())

    routes = RouteRegistry()
    routes.register(build_cash_register_route_definition())

    view_factories = ViewFactoryRegistry()

    dispatcher = DispatchingModuleActivator()
    dispatcher.register(CASH_REGISTER_MODULE_ID, CashRegisterModuleActivator(
        connection=conn, view_factory_registry=view_factories, session_context=session_context,
    ))
    loader = ModuleLoader(module_registry=modules, activator=dispatcher)

    router = DesktopRouter(
        route_registry=routes, view_factory_registry=view_factories,
        initial_context=_context(branch_id=branch_id, permissions=permissions),
    )
    return router, loader, view_factories


def test_route_graph_is_invalid_before_the_module_loads(app, conn, branch_id):
    session = _FakeSession(user_id="user-1", branch_id=branch_id)
    router, loader, view_factories = _wire(conn, branch_id, permissions={"CAJA.VER"}, session_context=session)
    modules = ModuleRegistry()
    modules.register(build_cash_register_module_descriptor())
    issues = RouteRegistryValidator().validate(router.route_registry, modules, view_factories)
    assert any(i.code == "ROUTE_VIEW_FACTORY_NOT_FOUND" for i in issues)


def test_ensure_loaded_registers_the_view_factory(app, conn, branch_id):
    session = _FakeSession(user_id="user-1", branch_id=branch_id)
    router, loader, view_factories = _wire(conn, branch_id, permissions={"CAJA.VER"}, session_context=session)
    assert view_factories.is_registered("cash_register.workspace_view") is False
    result = loader.ensure_loaded(CASH_REGISTER_MODULE_ID)
    assert result.state is ModuleLoadState.LOADED
    assert view_factories.is_registered("cash_register.workspace_view") is True


def test_navigate_builds_a_real_cash_register_workspace(app, conn, branch_id):
    session = _FakeSession(user_id="user-1", branch_id=branch_id)
    router, loader, view_factories = _wire(conn, branch_id, permissions={"CAJA.VER"}, session_context=session)
    loader.ensure_loaded(CASH_REGISTER_MODULE_ID)

    result = router.navigate(CASH_REGISTER_ROUTE_ID)
    assert isinstance(result.view, CashRegisterWorkspace)
    assert result.route.breadcrumb == ("Caja",)


def test_navigate_without_the_required_permission_is_denied(app, conn, branch_id):
    session = _FakeSession(user_id="user-1", branch_id=branch_id)
    router, loader, view_factories = _wire(conn, branch_id, permissions=set(), session_context=session)
    loader.ensure_loaded(CASH_REGISTER_MODULE_ID)
    with pytest.raises(NavigationPermissionDeniedError):
        router.navigate(CASH_REGISTER_ROUTE_ID)


def test_stand_in_never_leaks_into_the_real_container_module(app, conn, branch_id):
    # Structural guard for this module's own reason for existing: the
    # activator's constructor only accepts named, narrow dependencies.
    import inspect

    params = list(inspect.signature(CashRegisterModuleActivator.__init__).parameters)
    assert "container" not in params

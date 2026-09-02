"""SHELL-16 end-to-end proof — customers_crm navigable through the real
SHELL-8..15 shell (ModuleRegistry, RouteRegistry, ViewFactoryRegistry,
ModuleLoader, DesktopRouter), built from a real, migrated SQLite
connection and a real permission-bearing session — never a whole
dependency container anywhere in the chain.

Headless (offscreen Qt). Schema setup mirrors `tests/integration/customers/conftest.py::full_crm_conn`
(the five Clientes/CRM sub-bounded-context schemas + the read-only legacy
`cuentas_por_cobrar` shape) — that fixture is scoped to its own directory,
so it's replicated here rather than cross-directory-imported.
"""
from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.application.customers.permissions import CustomerPermissions  # noqa: E402
from backend.bootstrap.application_context import ApplicationContext, FeatureContext  # noqa: E402
from backend.infrastructure.db.schema.crm_schema import create_crm_schema  # noqa: E402
from backend.infrastructure.db.schema.customer_credit_schema import (  # noqa: E402
    create_customer_credit_schema,
)
from backend.infrastructure.db.schema.customer_privacy_schema import (  # noqa: E402
    create_customer_privacy_schema,
)
from backend.infrastructure.db.schema.customer_service_schema import (  # noqa: E402
    create_customer_service_schema,
)
from backend.infrastructure.db.schema.customers_crm_schema import create_customers_crm_schema  # noqa: E402
from frontend.desktop.modules.customers_crm.customers_crm_workspace import CustomersCrmWorkspace  # noqa: E402
from frontend.desktop.modules.customers_crm.shell_registration import (  # noqa: E402
    CUSTOMERS_CRM_MODULE_ID,
    CUSTOMERS_CRM_ROUTE_ID,
    CustomersCrmModuleActivator,
    build_customers_crm_module_descriptor,
    build_customers_crm_route_definition,
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

_CXC_DDL = """
CREATE TABLE IF NOT EXISTS cuentas_por_cobrar (
    id TEXT NOT NULL PRIMARY KEY,
    cliente_id TEXT NOT NULL,
    venta_id TEXT,
    folio TEXT,
    monto_original REAL NOT NULL,
    saldo_pendiente REAL NOT NULL,
    estado TEXT DEFAULT 'pendiente',
    sucursal_id TEXT,
    fecha DATETIME DEFAULT (datetime('now')),
    fecha_pago DATETIME
)
"""


class _FakeSession:
    def __init__(self, grants=(), *, user_id="u1", active_branch_id="b1"):
        self._grants = set(grants)
        self.is_active = True
        self.user_id = user_id
        self.active_branch_id = active_branch_id

    def tiene_permiso(self, code: str) -> bool:
        return code in self._grants


def _all_permissions_session() -> _FakeSession:
    return _FakeSession({v for v in vars(CustomerPermissions).values() if isinstance(v, str)})


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys = ON")
    create_customers_crm_schema(c)
    create_crm_schema(c)
    create_customer_service_schema(c)
    create_customer_credit_schema(c)
    create_customer_privacy_schema(c)
    c.execute(_CXC_DDL)
    c.commit()
    return c


def _context(*, branch_id, user_id, permissions) -> ApplicationContext:
    return ApplicationContext(
        installation_id="install-1", company_id="company-1", branch_id=branch_id,
        branch_name="Sucursal Centro", workstation_id="ws-1", workstation_type="pos",
        user_id=user_id, user_name="Agente", roles=("cajero",),
        permissions=frozenset(permissions), feature_context=FeatureContext(),
        session_id="session-1",
    )


def _wire(conn, session) -> tuple[DesktopRouter, ModuleLoader, ViewFactoryRegistry]:
    modules = ModuleRegistry()
    modules.register(build_customers_crm_module_descriptor())

    routes = RouteRegistry()
    routes.register(build_customers_crm_route_definition())

    view_factories = ViewFactoryRegistry()

    dispatcher = DispatchingModuleActivator()
    dispatcher.register(CUSTOMERS_CRM_MODULE_ID, CustomersCrmModuleActivator(
        connection=conn, view_factory_registry=view_factories, session_context=session,
    ))
    loader = ModuleLoader(module_registry=modules, activator=dispatcher)

    context = _context(branch_id=session.active_branch_id, user_id=session.user_id, permissions={"CLIENTES_CRM.VER"})
    router = DesktopRouter(route_registry=routes, view_factory_registry=view_factories, initial_context=context)
    return router, loader, view_factories


def test_route_graph_is_invalid_before_the_module_loads(app, conn):
    session = _all_permissions_session()
    router, loader, view_factories = _wire(conn, session)
    modules = ModuleRegistry()
    modules.register(build_customers_crm_module_descriptor())
    issues = RouteRegistryValidator().validate(router.route_registry, modules, view_factories)
    assert any(i.code == "ROUTE_VIEW_FACTORY_NOT_FOUND" for i in issues)


def test_ensure_loaded_registers_the_view_factory(app, conn):
    session = _all_permissions_session()
    router, loader, view_factories = _wire(conn, session)
    assert view_factories.is_registered("customers_crm.workspace_view") is False
    result = loader.ensure_loaded(CUSTOMERS_CRM_MODULE_ID)
    assert result.state is ModuleLoadState.LOADED
    assert view_factories.is_registered("customers_crm.workspace_view") is True


def test_navigate_builds_a_real_customers_crm_workspace(app, conn):
    session = _all_permissions_session()
    router, loader, view_factories = _wire(conn, session)
    loader.ensure_loaded(CUSTOMERS_CRM_MODULE_ID)

    result = router.navigate(CUSTOMERS_CRM_ROUTE_ID)
    assert isinstance(result.view, CustomersCrmWorkspace)
    assert result.route.breadcrumb == ("Clientes", "Clientes y CRM")


def test_navigate_without_the_required_permission_is_denied(app, conn):
    modules = ModuleRegistry()
    modules.register(build_customers_crm_module_descriptor())
    routes = RouteRegistry()
    routes.register(build_customers_crm_route_definition())
    view_factories = ViewFactoryRegistry()

    session = _all_permissions_session()
    dispatcher = DispatchingModuleActivator()
    dispatcher.register(CUSTOMERS_CRM_MODULE_ID, CustomersCrmModuleActivator(
        connection=conn, view_factory_registry=view_factories, session_context=session,
    ))
    loader = ModuleLoader(module_registry=modules, activator=dispatcher)
    loader.ensure_loaded(CUSTOMERS_CRM_MODULE_ID)

    context = _context(branch_id=session.active_branch_id, user_id=session.user_id, permissions=set())
    router = DesktopRouter(route_registry=routes, view_factory_registry=view_factories, initial_context=context)

    with pytest.raises(NavigationPermissionDeniedError):
        router.navigate(CUSTOMERS_CRM_ROUTE_ID)

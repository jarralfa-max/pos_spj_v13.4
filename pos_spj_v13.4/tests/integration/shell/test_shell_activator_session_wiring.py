"""`orders_delivery` y `business_intelligence`: el sidebar interno dejaba de
existir porque el activator leía la sesión con los nombres equivocados.

A diferencia de `losses`/`meat_processing` (ver sus propios
`test_*_module_migration.py`), estos dos NO duplicaban la composición: sus
vistas arman su propio `page_builder` a partir de
`connection`/`branch_id`/`actor_user_id`. El defecto era sólo —y bastaba—
la lectura de la sesión: un `_has_permission` copiado en ambos archivos que
sondeaba `has_permission`/`permissions`, atributos que NI `SessionContext`
NI `LegacySessionAdapter` definen (ambos hablan `tiene_permiso`/`permisos`).

Consecuencia medible: `visible_entries()` no devolvía ninguna entrada, el
sidebar quedaba vacío y con él las 10 rutas REALES de BI eran inalcanzables
por el shell.

Ambos activators usan ahora `frontend/desktop/shell/modules/session_access.py`
(probado aparte en `tests/unit/shell/test_session_access.py`).
"""
from __future__ import annotations

import ast
import os
import sqlite3
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions  # noqa: E402
from backend.bootstrap.application_context import ApplicationContext, FeatureContext  # noqa: E402

from frontend.desktop.modules.business_intelligence.navigation.business_intelligence_sidebar import (  # noqa: E402
    BUSINESS_INTELLIGENCE_NAV,
)
from frontend.desktop.modules.business_intelligence.shell_registration import (  # noqa: E402
    BUSINESS_INTELLIGENCE_MODULE_ID,
    BUSINESS_INTELLIGENCE_ROUTE_ID,
    BusinessIntelligenceModuleActivator,
    build_business_intelligence_module_descriptor,
    build_business_intelligence_route_definition,
)
from frontend.desktop.modules.orders_delivery.navigation.orders_delivery_sidebar import (  # noqa: E402
    ORDERS_DELIVERY_NAV,
)
from frontend.desktop.modules.orders_delivery.shell_registration import (  # noqa: E402
    ORDERS_DELIVERY_MODULE_ID,
    ORDERS_DELIVERY_ROUTE_ID,
    OrdersDeliveryModuleActivator,
    build_orders_delivery_module_descriptor,
    build_orders_delivery_route_definition,
)
from frontend.desktop.shell.loading.dispatching_module_activator import DispatchingModuleActivator  # noqa: E402
from frontend.desktop.shell.loading.module_load_state import ModuleLoadState  # noqa: E402
from frontend.desktop.shell.loading.module_loader import ModuleLoader  # noqa: E402
from frontend.desktop.shell.modules.module_registry import ModuleRegistry  # noqa: E402
from frontend.desktop.shell.router.desktop_router import DesktopRouter  # noqa: E402
from frontend.desktop.shell.routing.route_registry import RouteRegistry  # noqa: E402
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]

# Rutas SIN página real: construirlas no consulta la base, así que sirven
# como primera entrada visible del sidebar sin montar un esquema completo.
BI_PLACEHOLDER_ROUTE = "bi_production"
OD_PLACEHOLDER_ROUTE = "orders_new"


def _permission_for(nav, page_id):
    return next(entry.permission for entry in nav if entry.page_id == page_id)


class _SpanishApiSession:
    """Mismo subconjunto que `SessionContext` y `LegacySessionAdapter`."""

    user_id = "u1"
    is_active = True
    active_branch_id = "b1"
    sucursal_id = "b1"

    def __init__(self, permisos=frozenset()):
        self.permisos = frozenset(permisos)

    def tiene_permiso(self, code):
        return code in self.permisos


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def _context(*, permissions) -> ApplicationContext:
    return ApplicationContext(
        installation_id="install-1", company_id="company-1", branch_id="b1",
        branch_name="Matriz", workstation_id="ws-1", workstation_type="pos",
        user_id="u1", user_name="Analista", roles=("analista",),
        permissions=frozenset(normalize_permission(c) for c in permissions),
        feature_context=FeatureContext(), session_id="session-1",
    )


def _navigate(conn, *, descriptor, route, activator_cls, module_id, route_id, session):
    modules = ModuleRegistry()
    modules.register(descriptor)
    routes = RouteRegistry()
    routes.register(route)
    view_factories = ViewFactoryRegistry()

    dispatcher = DispatchingModuleActivator()
    dispatcher.register(module_id, activator_cls(
        connection=conn, view_factory_registry=view_factories, session_context=session))
    loader = ModuleLoader(module_registry=modules, activator=dispatcher)
    assert loader.ensure_loaded(module_id).state is ModuleLoadState.LOADED

    router = DesktopRouter(
        route_registry=routes, view_factory_registry=view_factories,
        initial_context=_context(permissions={route.required_permission}),
    )
    return router.navigate(route_id).view


def _navigate_bi(conn, session):
    return _navigate(
        conn,
        descriptor=build_business_intelligence_module_descriptor(),
        route=build_business_intelligence_route_definition(),
        activator_cls=BusinessIntelligenceModuleActivator,
        module_id=BUSINESS_INTELLIGENCE_MODULE_ID,
        route_id=BUSINESS_INTELLIGENCE_ROUTE_ID,
        session=session,
    )


def _navigate_od(conn, session):
    return _navigate(
        conn,
        descriptor=build_orders_delivery_module_descriptor(),
        route=build_orders_delivery_route_definition(),
        activator_cls=OrdersDeliveryModuleActivator,
        module_id=ORDERS_DELIVERY_MODULE_ID,
        route_id=ORDERS_DELIVERY_ROUTE_ID,
        session=session,
    )


# ── El defecto, medido en el sidebar ──────────────────────────────────────

def test_bi_sidebar_is_populated_from_a_spanish_api_session(app, conn):
    permission = _permission_for(BUSINESS_INTELLIGENCE_NAV, BI_PLACEHOLDER_ROUTE)
    view = _navigate_bi(conn, _SpanishApiSession({permission}))
    assert view.sidebar.count() == 1
    assert view.active_route == BI_PLACEHOLDER_ROUTE


def test_orders_delivery_sidebar_is_populated_from_a_spanish_api_session(app, conn):
    permission = _permission_for(ORDERS_DELIVERY_NAV, OD_PLACEHOLDER_ROUTE)
    view = _navigate_od(conn, _SpanishApiSession({permission}))
    assert view.sidebar.count() == 1
    assert view.active_route == OD_PLACEHOLDER_ROUTE


@pytest.mark.parametrize("navigate", [_navigate_bi, _navigate_od])
def test_a_session_without_permissions_still_sees_nothing(app, conn, navigate):
    """La corrección no afloja el filtro: sin permisos, sidebar vacío."""
    assert navigate(conn, _SpanishApiSession()).sidebar.count() == 0


@pytest.mark.parametrize("navigate", [_navigate_bi, _navigate_od])
def test_no_session_grants_nothing(app, conn, navigate):
    assert navigate(conn, None).sidebar.count() == 0


# ── La sesión llega completa a la vista, que es quien compone ─────────────

@pytest.mark.parametrize(
    "module_path, view_name",
    [
        ("frontend.desktop.modules.business_intelligence.business_intelligence_view",
         "BusinessIntelligenceView"),
        ("frontend.desktop.modules.orders_delivery.orders_delivery_view",
         "OrdersDeliveryView"),
    ],
)
def test_activator_hands_the_view_connection_branch_and_actor(
    app, conn, monkeypatch, module_path, view_name,
):
    """Las páginas reales de ambos módulos sólo se construyen si la vista
    recibe `connection` y `branch_id` (ver `_REAL_ROUTE_BUILDERS` y, en
    orders_delivery, su comprobación explícita de `branch_id is not None`).
    """
    import importlib

    module = importlib.import_module(module_path)
    captured = {}

    class _Recorder:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(module, view_name, _Recorder)

    session = _SpanishApiSession({"CUALQUIERA"})
    if view_name == "BusinessIntelligenceView":
        activator = BusinessIntelligenceModuleActivator(
            connection=conn, view_factory_registry=ViewFactoryRegistry(),
            session_context=session)
    else:
        activator = OrdersDeliveryModuleActivator(
            connection=conn, view_factory_registry=ViewFactoryRegistry(),
            session_context=session)
    activator._build_view()

    assert captured["connection"] is conn
    assert captured["branch_id"] == "b1"
    assert captured["actor_user_id"] == "u1"
    assert captured["has_permission"]("CUALQUIERA") is True
    assert captured["has_permission"]("OTRA") is False


# ── Guardrail de fuente ───────────────────────────────────────────────────

def test_no_activator_reimplements_the_session_reading():
    """Sobre el AST: los docstrings NOMBRAN los atributos ingleses que se
    retiraron, y un `in source` los marcaría como si siguieran en uso."""
    offenders = []
    for path in (ROOT / "frontend/desktop/modules").glob("*/shell_registration.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Name) and node.func.id == "getattr"):
                continue
            if len(node.args) < 2 or not isinstance(node.args[1], ast.Constant):
                continue
            if node.args[1].value in ("has_permission", "permissions"):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        "Ninguna sesión viva define `has_permission`/`permissions`; usa "
        f"frontend/desktop/shell/modules/session_access.py. Offenders: {offenders}")

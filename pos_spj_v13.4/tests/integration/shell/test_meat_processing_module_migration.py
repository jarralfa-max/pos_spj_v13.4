"""Procesamiento Cárnico: prueba de que el shell nuevo y el
`MeatProcessingModuleHost` comparten UNA sola composición (§3), no dos.

Hermana de `test_losses_module_migration.py`, que documenta el mismo defecto
en Mermas. Aquí el activator construía su propio
`MeatProcessingView(page_builder=build_page)`:

  * las 29 rutas caían en `MeatProcessingPlaceholderPage`, incluida
    `mp_processing_orders`, que sí tiene página real con presenter y los
    cuatro casos de uso del ciclo de vida de la orden;
  * su `_has_permission` sondeaba `has_permission`/`permissions`, atributos
    que NI `SessionContext` NI `LegacySessionAdapter` definen —ambos hablan
    `tiene_permiso`/`permisos`—, así que el sidebar salía siempre vacío.

Headless (offscreen Qt), conexión SQLite real, nunca un contenedor completo.
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

from backend.application.meat_processing.permissions import MeatProcessingPermissions  # noqa: E402
from backend.bootstrap.application_context import ApplicationContext, FeatureContext  # noqa: E402
from backend.security.permissions.codes import normalize_permission  # noqa: E402

from backend.domain.meat_processing.slaughter.feature_flag import SLAUGHTER_ENABLED  # noqa: E402
from backend.infrastructure.desktop.meat_processing_factory import (  # noqa: E402
    create_meat_processing_view,
)
from frontend.desktop.modules.meat_processing.meat_processing_view import MeatProcessingView  # noqa: E402
from frontend.desktop.modules.meat_processing.navigation.meat_processing_sidebar import (  # noqa: E402
    MEAT_PROCESSING_NAV,
    SLAUGHTER_FEATURE_FLAG,
)
from frontend.desktop.modules.meat_processing.pages import (  # noqa: E402
    MeatProcessingPlaceholderPage,
    ProcessingOrdersPage,
)
from frontend.desktop.modules.meat_processing.shell_registration import (  # noqa: E402
    MEAT_PROCESSING_MODULE_ID,
    MEAT_PROCESSING_ROUTE_ID,
    MeatProcessingModuleActivator,
    build_meat_processing_module_descriptor,
    build_meat_processing_route_definition,
)
from frontend.desktop.shell.loading.dispatching_module_activator import DispatchingModuleActivator  # noqa: E402
from frontend.desktop.shell.loading.module_load_state import ModuleLoadState  # noqa: E402
from frontend.desktop.shell.loading.module_loader import ModuleLoader  # noqa: E402
from frontend.desktop.shell.modules.module_registry import ModuleRegistry  # noqa: E402
from frontend.desktop.shell.router.desktop_router import DesktopRouter  # noqa: E402
from frontend.desktop.shell.router.errors import NavigationPermissionDeniedError  # noqa: E402
from frontend.desktop.shell.routing.route_registry import RouteRegistry  # noqa: E402
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]

# Única ruta con página real hoy. Las otras 28 son placeholder legítimo y el
# módulo SIGUE en `_PLACEHOLDER_BACKED` por ellas.
REAL_PAGE_ID = "mp_processing_orders"

# Sólo "Resumen" visible: su página es placeholder y no dispara consultas al
# construirse. `MeatProcessingView.__init__` abre la primera entrada visible.
SIDEBAR_PERMISSIONS = frozenset({
    MeatProcessingPermissions.VIEW,
    MeatProcessingPermissions.DASHBOARD_VIEW,
})


class _FakeSession:
    """Mismo subconjunto que `SessionContext` y `LegacySessionAdapter`:
    API en español y `active_warehouse_id`."""

    user_id = "u1"
    is_active = True
    active_branch_id = "b1"
    sucursal_id = "b1"
    active_warehouse_id = "wh-9"

    def __init__(self, permissions=SIDEBAR_PERMISSIONS) -> None:
        self.permisos = frozenset(permissions)

    def tiene_permiso(self, code):
        return code in self.permisos


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def _called_names(path: Path) -> list[str]:
    """Nombres realmente invocados en un módulo — ignora docstrings."""
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.append(node.func.attr)
    return names


def _context(*, permissions) -> ApplicationContext:
    # `PermissionEvaluator` normaliza el código consultado a mayúsculas
    # (`PRODUCCION.ver` -> `PRODUCCION.VER`) y lo compara contra el conjunto
    # tal cual; un contexto real se construye ya normalizado.
    permissions = {normalize_permission(code) for code in permissions}
    return ApplicationContext(
        installation_id="install-1", company_id="company-1", branch_id="b1",
        branch_name="Matriz", workstation_id="ws-1", workstation_type="pos",
        user_id="u1", user_name="Operario", roles=("operario",),
        permissions=frozenset(permissions), feature_context=FeatureContext(),
        session_id="session-1",
    )


def _wire(conn, *, permissions, session_context):
    modules = ModuleRegistry()
    modules.register(build_meat_processing_module_descriptor())

    routes = RouteRegistry()
    routes.register(build_meat_processing_route_definition())

    view_factories = ViewFactoryRegistry()

    dispatcher = DispatchingModuleActivator()
    dispatcher.register(MEAT_PROCESSING_MODULE_ID, MeatProcessingModuleActivator(
        connection=conn, view_factory_registry=view_factories,
        session_context=session_context,
    ))
    loader = ModuleLoader(module_registry=modules, activator=dispatcher)

    router = DesktopRouter(
        route_registry=routes, view_factory_registry=view_factories,
        initial_context=_context(permissions=permissions),
    )
    return router, loader, view_factories


def _route_permission():
    return build_meat_processing_route_definition().required_permission


def _navigate(conn, *, session=None):
    session = session or _FakeSession()
    router, loader, _ = _wire(
        conn, permissions={_route_permission()}, session_context=session)
    assert loader.ensure_loaded(MEAT_PROCESSING_MODULE_ID).state is ModuleLoadState.LOADED
    return router.navigate(MEAT_PROCESSING_ROUTE_ID).view


def test_ensure_loaded_registers_the_view_factory(app, conn):
    _, loader, view_factories = _wire(
        conn, permissions={_route_permission()}, session_context=_FakeSession())
    assert view_factories.is_registered("meat_processing.workspace_view") is False
    assert loader.ensure_loaded(
        MEAT_PROCESSING_MODULE_ID).state is ModuleLoadState.LOADED
    assert view_factories.is_registered("meat_processing.workspace_view") is True


def test_navigate_builds_a_real_meat_processing_view(app, conn):
    assert isinstance(_navigate(conn), MeatProcessingView)


def test_create_meat_processing_view_takes_plain_dependencies(app, conn):
    """La factory pública no recibe contenedor: conexión y sesión, ya
    desempaquetadas (§5)."""
    view = create_meat_processing_view(conn, _FakeSession())
    assert isinstance(view, MeatProcessingView)
    assert isinstance(view._page_builder(REAL_PAGE_ID), ProcessingOrdersPage)


def test_navigate_without_the_required_permission_is_denied(app, conn):
    router, loader, _ = _wire(conn, permissions=set(), session_context=_FakeSession())
    loader.ensure_loaded(MEAT_PROCESSING_MODULE_ID)
    with pytest.raises(NavigationPermissionDeniedError):
        router.navigate(MEAT_PROCESSING_ROUTE_ID)


def test_shell_sidebar_reads_a_spanish_api_session(app, conn):
    """Regresión del sidebar vacío: `tiene_permiso`, no `has_permission`."""
    assert _navigate(conn).sidebar.count() >= 1
    assert _navigate(
        conn, session=_FakeSession(permissions=frozenset())).sidebar.count() == 0


def test_the_orders_page_is_real_through_the_shell(app, conn):
    """El corazón de §3: la composición única sirve la página real, con
    presenter, no el placeholder."""
    # A través del router real, no llamando la factory a mano: es la ruta
    # del shell la que antes servía un placeholder aquí.
    page = _navigate(conn)._page_builder(REAL_PAGE_ID)
    assert isinstance(page, ProcessingOrdersPage)
    assert not isinstance(page, MeatProcessingPlaceholderPage)


def test_the_remaining_routes_are_still_honest_placeholders(app, conn):
    """No se declara más avance del real: 28 de 29 siguen sin página."""
    view = _navigate(conn)
    pending = [e.page_id for e in MEAT_PROCESSING_NAV if e.page_id != REAL_PAGE_ID]
    assert len(pending) == 28
    for page_id in pending:
        assert isinstance(
            view._page_builder(page_id), MeatProcessingPlaceholderPage), page_id


def test_slaughter_sections_follow_the_domain_constant_not_a_local_false(monkeypatch):
    """El `has_feature` del host era un `lambda _flag: False` escrito a mano:
    una SEGUNDA fuente de verdad para "¿hay sacrificio?", que se
    desincronizaría en cuanto alguien encendiera `SLAUGHTER_ENABLED`.

    Comprobar sólo el valor de hoy (False) no probaría nada —un `False`
    local pasaría igual—, así que se enciende la constante del dominio y se
    verifica que el sidebar la SIGUE."""
    from backend.infrastructure.desktop import meat_processing_factory as factory

    assert len([e for e in MEAT_PROCESSING_NAV
                if e.feature_flag == SLAUGHTER_FEATURE_FLAG]) == 10

    assert SLAUGHTER_ENABLED is False, (
        "si el sacrificio ya se implementó, esta prueba debe revisarse")
    assert factory._has_slaughter_feature(SLAUGHTER_FEATURE_FLAG) is False

    monkeypatch.setattr(factory, "SLAUGHTER_ENABLED", True)
    assert factory._has_slaughter_feature(SLAUGHTER_FEATURE_FLAG) is True
    # Una bandera ajena nunca se habilita, ni con sacrificio encendido.
    assert factory._has_slaughter_feature("otra_bandera") is False


def test_neither_host_composes_the_module_on_its_own():
    """Guardrail de fuente sobre el AST (los docstrings NOMBRAN la
    composición retirada; un `in source` la marcaría como viva)."""
    activator = _called_names(
        ROOT / "frontend/desktop/modules/meat_processing/shell_registration.py")
    assert "create_meat_processing_view" in activator
    assert "MeatProcessingView" not in activator
    assert "build_page" not in activator

    factory = _called_names(
        ROOT / "backend/infrastructure/desktop/meat_processing_factory.py")
    # Definida una vez, invocada desde los dos anfitriones.
    assert factory.count("_build_meat_processing_wiring") == 2

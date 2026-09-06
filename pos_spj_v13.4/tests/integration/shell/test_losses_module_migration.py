"""Mermas: prueba de que el shell nuevo y el slot `MERMAS` de `MainWindow`
comparten UNA sola composición (§3), no dos.

Antes de esta prueba `LossesModuleActivator._build_view()` construía su
propio `LossesView(page_builder=build_page)`. Eso era una segunda ruta
funcional del mismo dominio y era estrictamente PEOR que la canónica:

  * las 16 rutas caían en `LossesPlaceholderPage`, incluidas las 4 que sí
    tienen página real (`losses_registration`, `losses_investigations`,
    `losses_overview`, `losses_analysis`);
  * no construía ninguno de los 15 servicios del bounded context;
  * su `_has_permission` sondeaba `has_permission`/`permissions`, atributos
    que NI `SessionContext` NI `LegacySessionAdapter` definen —ambos hablan
    `tiene_permiso`/`permisos`—, así que el sidebar salía siempre vacío.

Headless (offscreen Qt), misma forma que
`test_transfers_module_migration.py`: conexión SQLite real y migrada, nunca
un contenedor de dependencias completo.
"""
from __future__ import annotations

import importlib
import os
import sqlite3
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[3]

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.application.losses.permissions import LossPermissions  # noqa: E402
from backend.bootstrap.application_context import ApplicationContext, FeatureContext  # noqa: E402
from backend.infrastructure.desktop.losses_factory import (  # noqa: E402
    build_losses_wiring,
    create_losses_view,
)
from frontend.desktop.modules.losses.losses_view import LossesView  # noqa: E402
from frontend.desktop.modules.losses.navigation.losses_sidebar import LOSSES_NAV  # noqa: E402
from frontend.desktop.modules.losses.pages import (  # noqa: E402
    LossAnalyticsPage,
    LossesPlaceholderPage,
    LossRegistrationPage,
    RootCausePage,
)
from frontend.desktop.modules.losses.shell_registration import (  # noqa: E402
    LOSSES_MODULE_ID,
    LOSSES_ROUTE_ID,
    LossesModuleActivator,
    build_losses_module_descriptor,
    build_losses_route_definition,
)
from frontend.desktop.shell.loading.dispatching_module_activator import DispatchingModuleActivator  # noqa: E402
from frontend.desktop.shell.loading.module_load_state import ModuleLoadState  # noqa: E402
from frontend.desktop.shell.loading.module_loader import ModuleLoader  # noqa: E402
from frontend.desktop.shell.modules.module_registry import ModuleRegistry  # noqa: E402
from frontend.desktop.shell.router.desktop_router import DesktopRouter  # noqa: E402
from frontend.desktop.shell.router.errors import NavigationPermissionDeniedError  # noqa: E402
from frontend.desktop.shell.routing.route_registry import RouteRegistry  # noqa: E402
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry  # noqa: E402


# Las 4 rutas con página real hoy; las otras 12 siguen siendo placeholder
# legítimo — este módulo NO sale de `_PLACEHOLDER_BACKED` por esta prueba.
REAL_PAGES = {
    "losses_registration": LossRegistrationPage,
    "losses_investigations": RootCausePage,
    "losses_overview": LossAnalyticsPage,
    "losses_analysis": LossAnalyticsPage,
}

# Sólo "Pendientes" visible: su página es placeholder y no dispara consultas
# al construirse. `LossesView.__init__` abre la primera entrada visible del
# sidebar, y abrir la de analítica ahí levantaría un QMessageBox modal.
SIDEBAR_PERMISSIONS = frozenset({LossPermissions.VIEW, LossPermissions.PENDING_VIEW})


class _FakeSession:
    """Expone el MISMO subconjunto que `SessionContext` y
    `LegacySessionAdapter`: API en español, `active_warehouse_id`."""

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
    importlib.import_module(
        "migrations.standalone.174_losses_bounded_context_schema"
    ).run(c)
    c.commit()
    return c


def _called_names(path: Path) -> list[str]:
    """Nombres realmente invocados en un módulo — ignora docstrings."""
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.append(func.id)
        elif isinstance(func, ast.Attribute):
            names.append(func.attr)
    return names


def _context(*, permissions) -> ApplicationContext:
    return ApplicationContext(
        installation_id="install-1", company_id="company-1", branch_id="b1",
        branch_name="Matriz", workstation_id="ws-1", workstation_type="pos",
        user_id="u1", user_name="Almacenista", roles=("almacenista",),
        permissions=frozenset(permissions), feature_context=FeatureContext(),
        session_id="session-1",
    )


def _wire(conn, *, permissions, session_context):
    modules = ModuleRegistry()
    modules.register(build_losses_module_descriptor())

    routes = RouteRegistry()
    routes.register(build_losses_route_definition())

    view_factories = ViewFactoryRegistry()

    dispatcher = DispatchingModuleActivator()
    dispatcher.register(LOSSES_MODULE_ID, LossesModuleActivator(
        connection=conn, view_factory_registry=view_factories,
        session_context=session_context,
    ))
    loader = ModuleLoader(module_registry=modules, activator=dispatcher)

    router = DesktopRouter(
        route_registry=routes, view_factory_registry=view_factories,
        initial_context=_context(permissions=permissions),
    )
    return router, loader, view_factories


def _navigate(conn, *, session=None):
    session = session or _FakeSession()
    router, loader, _ = _wire(
        conn, permissions={LossPermissions.VIEW}, session_context=session)
    assert loader.ensure_loaded(LOSSES_MODULE_ID).state is ModuleLoadState.LOADED
    return router.navigate(LOSSES_ROUTE_ID).view


def test_ensure_loaded_registers_the_view_factory(app, conn):
    _, loader, view_factories = _wire(
        conn, permissions={LossPermissions.VIEW}, session_context=_FakeSession())
    assert view_factories.is_registered("losses.workspace_view") is False
    assert loader.ensure_loaded(LOSSES_MODULE_ID).state is ModuleLoadState.LOADED
    assert view_factories.is_registered("losses.workspace_view") is True


def test_navigate_builds_a_real_losses_view(app, conn):
    assert isinstance(_navigate(conn), LossesView)


def test_navigate_without_the_required_permission_is_denied(app, conn):
    router, loader, _ = _wire(
        conn, permissions=set(), session_context=_FakeSession())
    loader.ensure_loaded(LOSSES_MODULE_ID)
    with pytest.raises(NavigationPermissionDeniedError):
        router.navigate(LOSSES_ROUTE_ID)


def test_shell_view_carries_the_bounded_context_services(app, conn):
    """El activator ya no construye una vista pelada: los 15 servicios que
    compone el host canónico llegan también por la ruta del shell."""
    view = _navigate(conn)
    for service in (
        "loss_inventory_service", "expiry_damage_service",
        "quality_inspection_service", "loss_recovery_service",
        "loss_disposition_service", "loss_investigation_service",
        "loss_root_cause_service", "loss_corrective_action_service",
        "loss_valuation_service", "loss_notification_router",
        "transfer_loss_service", "transfer_loss_requested_handler",
        "production_loss_service", "yield_monitoring_query_service",
        "production_completed_loss_handler",
    ):
        assert getattr(view, service, None) is not None, service


def test_shell_sidebar_reads_a_spanish_api_session(app, conn):
    """Regresión del sidebar vacío: `tiene_permiso`, no `has_permission`."""
    view = _navigate(conn)
    assert view.sidebar.count() == 1
    assert view.active_route == "losses_pending"

    denied = _navigate(conn, session=_FakeSession(permissions=frozenset()))
    assert denied.sidebar.count() == 0


def test_the_four_real_pages_are_reachable_not_placeholders(app, conn):
    """El corazón de §3: la composición única sirve páginas reales."""
    page_builder = build_losses_wiring(conn, _FakeSession()).page_builder
    for page_id, expected in REAL_PAGES.items():
        page = page_builder(page_id)
        assert isinstance(page, expected), page_id
        assert not isinstance(page, LossesPlaceholderPage), page_id


def test_the_remaining_routes_are_still_honest_placeholders(app, conn):
    """No se declara más avance del real: 12 de 16 siguen sin página."""
    page_builder = build_losses_wiring(conn, _FakeSession()).page_builder
    pending = [entry.page_id for entry in LOSSES_NAV if entry.page_id not in REAL_PAGES]
    assert len(pending) == 12
    for page_id in pending:
        assert isinstance(page_builder(page_id), LossesPlaceholderPage), page_id


def test_registration_page_receives_the_sessions_active_warehouse(app, conn):
    """§17: la composición leía `warehouse_id`, que ninguna de las dos
    sesiones vivas define, así que el formulario recibía siempre ""."""
    page = build_losses_wiring(conn, _FakeSession()).page_builder("losses_registration")
    assert page._warehouse_id == "wh-9"


def test_neither_host_composes_the_module_on_its_own():
    """Guardrail de fuente para §3: los DOS anfitriones —el activator del
    shell y el `LossesModuleHost` del slot `MERMAS`— delegan en
    `build_losses_wiring`. Si alguno vuelve a armar su propia vista, esto
    falla antes de que la divergencia llegue a producción."""
    # Sobre el AST, no sobre el texto: los docstrings de ambos archivos
    # NOMBRAN la composición duplicada que se retiró, y un `in source`
    # volvería a marcarla como si siguiera viva.
    called = _called_names(ROOT / "frontend/desktop/modules/losses/shell_registration.py")
    assert "create_losses_view" in called
    assert "LossesView" not in called
    assert "build_page" not in called

    factory = _called_names(ROOT / "backend/infrastructure/desktop/losses_factory.py")
    # Definida una vez, invocada desde los dos anfitriones.
    assert factory.count("build_losses_wiring") == 2


def test_create_losses_view_returns_a_wired_view(app, conn):
    view = create_losses_view(conn, _FakeSession())
    assert isinstance(view, LossesView)
    assert view.loss_notification_router is not None

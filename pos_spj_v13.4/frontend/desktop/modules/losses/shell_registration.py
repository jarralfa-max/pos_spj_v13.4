"""Losses (Mermas) registration into the new shell.

Parte del lote que el usuario pidió cablear explícitamente sabiendo que
todas sus rutas devuelven páginas placeholder hoy; la construcción de
las páginas reales queda para una sesión posterior.

Sigue la misma forma que `transfers/shell_registration.py`: descriptor,
route definition y activator con dependencias explícitas — nunca el
`AppContainer` legacy.

No se cablea en `main.py`/`MainWindow`/`MenuLateral` en esta ronda. El slot
`MERMAS` del menú legacy sigue siendo la ruta viva.
"""
from __future__ import annotations

from typing import Optional

from backend.application.losses.permissions import LossPermissions
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

LOSSES_MODULE_ID = "losses"
LOSSES_ROUTE_ID = "losses.workspace"
LOSSES_VIEW_FACTORY_ID = "losses.workspace_view"

LOSSES_REQUIRED_PERMISSION = LossPermissions.VIEW


def build_losses_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=LOSSES_MODULE_ID,
        display_name="Mermas y Pérdidas",
        startup_mode=StartupMode.LAZY,
        routes=(LOSSES_ROUTE_ID,),
        permissions=frozenset({LOSSES_REQUIRED_PERMISSION}),
    )


def build_losses_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=LOSSES_ROUTE_ID,
        module_id=LOSSES_MODULE_ID,
        title="Mermas y Pérdidas",
        view_factory_id=LOSSES_VIEW_FACTORY_ID,
        breadcrumb=("Mermas y Pérdidas",),
        required_permission=LOSSES_REQUIRED_PERMISSION,
    )


class LossesModuleActivator:
    """`ModuleActivator` estructural (SHELL-13), misma convención que los
    once activators ya migrados."""

    def __init__(
        self, *, connection, view_factory_registry, session_context: Optional[object] = None,
    ) -> None:
        self._connection = connection
        self._session_context = session_context
        self._view_factories = view_factory_registry

    def _has_permission(self, permission: str) -> bool:
        """Sin sesión no se concede nada: gobierna el sidebar interno del
        módulo y mostrar de más sería peor que mostrar de menos."""
        session = self._session_context
        if session is None:
            return False
        checker = getattr(session, "has_permission", None)
        if callable(checker):
            return bool(checker(permission))
        permissions = getattr(session, "permissions", None)
        if permissions is None:
            return False
        return "*" in permissions or permission.upper() in {str(p).upper() for p in permissions}

    def _build_view(self):
        from frontend.desktop.modules.losses.losses_routes import build_page
        from frontend.desktop.modules.losses.losses_view import LossesView

        return LossesView(has_permission=self._has_permission, page_builder=build_page)


    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(LOSSES_VIEW_FACTORY_ID, self._build_view)

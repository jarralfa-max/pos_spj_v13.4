"""Losses (Mermas) registration into the new shell.

CORRECCIÓN DE LA MEDICIÓN ANTERIOR: se cableó este módulo creyendo que
"todas sus rutas devuelven páginas placeholder". Eso se midió sobre
`losses_routes.build_page()`, que en efecto devuelve placeholder siempre,
pero NO es el constructor de páginas que usa el módulo: el composition root
(`losses_factory.py`) pasa su propio `page_builder` con 4 rutas reales
—`losses_registration`, `losses_investigations`, `losses_overview` y
`losses_analysis`—. Siguen siendo placeholder las otras 12.

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

    def _build_view(self):
        """Delega en la ÚNICA composición del dominio, la misma que sirve al
        slot `MERMAS` de `MainWindow`.

        Antes este activator construía `LossesView(page_builder=build_page)`
        por su cuenta y eso era una SEGUNDA composición, estrictamente peor
        que la canónica (§3): sin servicios, sin presenters, con las 16 rutas
        en placeholder —incluidas las 4 que sí tienen página real— y con un
        `_has_permission` que sondeaba `has_permission`/`permissions`, atributos
        que ni `SessionContext` ni `LegacySessionAdapter` definen (ambos hablan
        `tiene_permiso`/`permisos`), de modo que el sidebar salía vacío.
        """
        from backend.infrastructure.desktop.losses_factory import create_losses_view

        return create_losses_view(self._connection, self._session_context)


    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(LOSSES_VIEW_FACTORY_ID, self._build_view)

"""Meat Processing (Producción) registration into the new shell.

Parte del lote que el usuario pidió cablear explícitamente sabiendo que
todas sus rutas devuelven páginas placeholder hoy; la construcción de
las páginas reales queda para una sesión posterior.

Sigue la misma forma que `transfers/shell_registration.py`: descriptor,
route definition y activator con dependencias explícitas — nunca el
`AppContainer` legacy.

No se cablea en `main.py`/`MainWindow`/`MenuLateral` en esta ronda. El slot
`PRODUCCION` del menú legacy sigue siendo la ruta viva.
"""
from __future__ import annotations

from typing import Optional

from backend.application.meat_processing.permissions import MeatProcessingPermissions
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

MEAT_PROCESSING_MODULE_ID = "meat_processing"
MEAT_PROCESSING_ROUTE_ID = "meat_processing.workspace"
MEAT_PROCESSING_VIEW_FACTORY_ID = "meat_processing.workspace_view"

MEAT_PROCESSING_REQUIRED_PERMISSION = MeatProcessingPermissions.VIEW


def build_meat_processing_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=MEAT_PROCESSING_MODULE_ID,
        display_name="Producción",
        startup_mode=StartupMode.LAZY,
        routes=(MEAT_PROCESSING_ROUTE_ID,),
        permissions=frozenset({MEAT_PROCESSING_REQUIRED_PERMISSION}),
    )


def build_meat_processing_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=MEAT_PROCESSING_ROUTE_ID,
        module_id=MEAT_PROCESSING_MODULE_ID,
        title="Producción",
        view_factory_id=MEAT_PROCESSING_VIEW_FACTORY_ID,
        breadcrumb=("Producción",),
        required_permission=MEAT_PROCESSING_REQUIRED_PERMISSION,
    )


class MeatProcessingModuleActivator:
    """`ModuleActivator` estructural (SHELL-13), misma convención que los
    once activators ya migrados."""

    def __init__(
        self, *, connection, view_factory_registry, session_context: Optional[object] = None,
    ) -> None:
        self._connection = connection
        self._session_context = session_context
        self._view_factories = view_factory_registry

    def _build_view(self):
        """Delega en la ÚNICA composición del dominio, la misma que consume
        el `MeatProcessingModuleHost` del slot legacy.

        Antes este activator armaba su propio
        `MeatProcessingView(page_builder=build_page)`, y eso era una SEGUNDA
        composición estrictamente peor que la canónica (§3): las 29 rutas en
        placeholder —incluida `mp_processing_orders`, que sí tiene página
        real con presenter y casos de uso—, y un `_has_permission` que
        sondeaba `has_permission`/`permissions`, atributos que ni
        `SessionContext` ni `LegacySessionAdapter` definen (ambos hablan
        `tiene_permiso`/`permisos`), de modo que el sidebar salía vacío.
        """
        from backend.infrastructure.desktop.meat_processing_factory import (
            create_meat_processing_view,
        )

        return create_meat_processing_view(self._connection, self._session_context)


    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(MEAT_PROCESSING_VIEW_FACTORY_ID, self._build_view)

"""Tarjetas de Fidelidad registration into the new shell.

Parte del lote que el usuario pidió cablear explícitamente sabiendo que
parte de sus páginas siguen siendo placeholder; su relleno queda para
una sesión posterior.

Sigue la misma forma que `transfers/shell_registration.py`: descriptor,
route definition y activator con dependencias explícitas — nunca el
`AppContainer` legacy.

No se cablea en `main.py`/`MainWindow`/`MenuLateral` en esta ronda. El slot
`TARJETAS_FIDELIDAD` del menú legacy sigue siendo la ruta viva.
"""
from __future__ import annotations

from typing import Optional

from backend.application.loyalty_cards.permissions import LoyaltyCardsPermissions
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

TARJETAS_FIDELIDAD_MODULE_ID = "tarjetas_fidelidad"
TARJETAS_FIDELIDAD_ROUTE_ID = "tarjetas_fidelidad.workspace"
TARJETAS_FIDELIDAD_VIEW_FACTORY_ID = "tarjetas_fidelidad.workspace_view"

TARJETAS_FIDELIDAD_REQUIRED_PERMISSION = LoyaltyCardsPermissions.VIEW


def build_tarjetas_fidelidad_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=TARJETAS_FIDELIDAD_MODULE_ID,
        display_name="Tarjetas de Fidelidad",
        startup_mode=StartupMode.LAZY,
        routes=(TARJETAS_FIDELIDAD_ROUTE_ID,),
        permissions=frozenset({TARJETAS_FIDELIDAD_REQUIRED_PERMISSION}),
    )


def build_tarjetas_fidelidad_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=TARJETAS_FIDELIDAD_ROUTE_ID,
        module_id=TARJETAS_FIDELIDAD_MODULE_ID,
        title="Tarjetas de Fidelidad",
        view_factory_id=TARJETAS_FIDELIDAD_VIEW_FACTORY_ID,
        breadcrumb=("Tarjetas de Fidelidad",),
        required_permission=TARJETAS_FIDELIDAD_REQUIRED_PERMISSION,
    )


class TarjetasFidelidadModuleActivator:
    """`ModuleActivator` estructural (SHELL-13), misma convención que los
    once activators ya migrados."""

    def __init__(
        self, *, connection, view_factory_registry, session_context: Optional[object] = None,
    ) -> None:
        self._connection = connection
        self._session_context = session_context
        self._view_factories = view_factory_registry

    def _build_view(self):
        from frontend.desktop.modules.tarjetas_fidelidad.composition import (
            create_tarjetas_fidelidad_view,
        )

        return create_tarjetas_fidelidad_view(self._connection, self._session_context)


    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(TARJETAS_FIDELIDAD_VIEW_FACTORY_ID, self._build_view)

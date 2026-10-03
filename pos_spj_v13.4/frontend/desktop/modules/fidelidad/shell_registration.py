"""Fidelidad registration into the shell.

LOY-29: todas sus rutas tienen página real, incluida la sección Tarjetas de
fidelidad (§5-6: no hay entrada global aparte para Tarjetas).

Sigue la misma forma que `transfers/shell_registration.py`: descriptor,
route definition y activator con dependencias explícitas — nunca el
`AppContainer` legacy.
"""
from __future__ import annotations

from typing import Optional

from backend.application.loyalty.permissions import LoyaltyPermissions
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

FIDELIDAD_MODULE_ID = "fidelidad"
FIDELIDAD_ROUTE_ID = "fidelidad.workspace"
FIDELIDAD_VIEW_FACTORY_ID = "fidelidad.workspace_view"

FIDELIDAD_REQUIRED_PERMISSION = LoyaltyPermissions.VIEW


def build_fidelidad_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=FIDELIDAD_MODULE_ID,
        display_name="Fidelidad",
        startup_mode=StartupMode.LAZY,
        routes=(FIDELIDAD_ROUTE_ID,),
        permissions=frozenset({FIDELIDAD_REQUIRED_PERMISSION}),
    )


def build_fidelidad_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=FIDELIDAD_ROUTE_ID,
        module_id=FIDELIDAD_MODULE_ID,
        title="Fidelidad",
        view_factory_id=FIDELIDAD_VIEW_FACTORY_ID,
        breadcrumb=("Fidelidad",),
        required_permission=FIDELIDAD_REQUIRED_PERMISSION,
    )


class FidelidadModuleActivator:
    """`ModuleActivator` estructural (SHELL-13), misma convención que los
    once activators ya migrados."""

    def __init__(
        self, *, connection, view_factory_registry, session_context: Optional[object] = None,
    ) -> None:
        self._connection = connection
        self._session_context = session_context
        self._view_factories = view_factory_registry

    def _build_view(self):
        from frontend.desktop.modules.fidelidad.composition import create_fidelidad_view

        return create_fidelidad_view(self._connection, self._session_context)


    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(FIDELIDAD_VIEW_FACTORY_ID, self._build_view)

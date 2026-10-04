"""Registro de Configuración en la shell viva.

Expone el descriptor del módulo, su ruta y un `ConfiguracionModuleActivator`
que recibe sólo dependencias explícitas (una conexión y la sesión), nunca el
`AppContainer` legacy. La vista la arma `configuracion_routes.build_configuracion_view`,
la ÚNICA composición del módulo: antes este archivo repetía las 84
dependencias del presenter y era el único camino que no filtraba el menú
interno por permisos.
"""
from __future__ import annotations

from typing import Optional

from backend.application.configuracion.permissions import ConfiguracionPermissions
from frontend.desktop.modules.configuracion.configuracion_routes import build_configuracion_view
from frontend.desktop.modules.configuracion.configuracion_view import ConfiguracionView
from frontend.desktop.modules.configuracion.navigation.configuracion_sidebar import CONFIGURACION_NAV
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

CONFIGURACION_MODULE_ID = "configuracion"
CONFIGURACION_ROUTE_ID = "configuracion.workspace"
CONFIGURACION_VIEW_FACTORY_ID = "configuracion.workspace_view"

CONFIGURACION_REQUIRED_PERMISSION = ConfiguracionPermissions.GENERAL_VIEW


def build_configuracion_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=CONFIGURACION_MODULE_ID,
        display_name="Configuración",
        startup_mode=StartupMode.LAZY,
        routes=(CONFIGURACION_ROUTE_ID,),
        permissions=frozenset({entry.permission for entry in CONFIGURACION_NAV}),
    )


def build_configuracion_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=CONFIGURACION_ROUTE_ID,
        module_id=CONFIGURACION_MODULE_ID,
        title="Configuración",
        view_factory_id=CONFIGURACION_VIEW_FACTORY_ID,
        breadcrumb=("Configuración",),
        required_permission=CONFIGURACION_REQUIRED_PERMISSION,
    )


class ConfiguracionModuleActivator:
    """A `ModuleActivator` (SHELL-13) — structural, not inherited."""

    def __init__(
        self, *, connection, view_factory_registry, session_context: Optional[object] = None,
    ) -> None:
        self._connection = connection
        self._session_context = session_context
        self._view_factories = view_factory_registry

    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(CONFIGURACION_VIEW_FACTORY_ID, self._build_view)

    def _build_view(self) -> ConfiguracionView:
        return build_configuracion_view(
            connection=self._connection, session_context=self._session_context)

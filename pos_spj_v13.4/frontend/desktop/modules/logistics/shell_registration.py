"""Logística en el shell (integración Logística 32cfbf).

Antes Logística sólo existía como una página de Compras: sin catálogo de
contenedores, sin lista de embarques y sin entrada propia. Módulo `logistics`,
gobernado por su propia capacidad instalable (`install_profile.py`).
"""
from __future__ import annotations

from typing import Optional

from backend.application.logistics.authorization import LogisticsPermissions
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

LOGISTICS_MODULE_ID = "logistics"
LOGISTICS_ROUTE_ID = "logistics.workspace"
LOGISTICS_VIEW_FACTORY_ID = "logistics.workspace_view"
LOGISTICS_REQUIRED_PERMISSION = LogisticsPermissions.SHIPMENT_VIEW


def build_logistics_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=LOGISTICS_MODULE_ID, display_name="Logística",
        startup_mode=StartupMode.LAZY, routes=(LOGISTICS_ROUTE_ID,),
        permissions=frozenset({LOGISTICS_REQUIRED_PERMISSION}))


def build_logistics_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=LOGISTICS_ROUTE_ID, module_id=LOGISTICS_MODULE_ID, title="Logística",
        view_factory_id=LOGISTICS_VIEW_FACTORY_ID, breadcrumb=("Logística",),
        required_permission=LOGISTICS_REQUIRED_PERMISSION)


class LogisticsModuleActivator:
    def __init__(self, *, connection, view_factory_registry,
                 session_context: Optional[object] = None) -> None:
        self._connection = connection
        self._session_context = session_context
        self._view_factories = view_factory_registry

    def _build_view(self):
        from backend.infrastructure.desktop.logistics_factory import create_logistics_view
        return create_logistics_view(self._connection, self._session_context)

    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(LOGISTICS_VIEW_FACTORY_ID, self._build_view)

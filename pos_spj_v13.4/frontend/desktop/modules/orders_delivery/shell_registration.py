"""Orders / Delivery (Pedidos y Reparto) registration into the new shell.

Parte del lote que el usuario pidió cablear explícitamente sabiendo que
sólo 3 de sus 23 rutas construyen páginas reales; las otras 20 caen a
placeholder. Su relleno queda para una sesión posterior.

Sigue la misma forma que `transfers/shell_registration.py`: descriptor,
route definition y activator con dependencias explícitas — nunca el
`AppContainer` legacy.

No se cablea en `main.py`/`MainWindow`/`MenuLateral` en esta ronda. El slot
`DELIVERY` del menú legacy sigue siendo la ruta viva.
"""
from __future__ import annotations

from typing import Optional

from backend.application.orders_delivery.permissions import OrdersDeliveryPermissions
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

ORDERS_DELIVERY_MODULE_ID = "orders_delivery"
ORDERS_DELIVERY_ROUTE_ID = "orders_delivery.workspace"
ORDERS_DELIVERY_VIEW_FACTORY_ID = "orders_delivery.workspace_view"

ORDERS_DELIVERY_REQUIRED_PERMISSION = OrdersDeliveryPermissions.ACCESS


def build_orders_delivery_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=ORDERS_DELIVERY_MODULE_ID,
        display_name="Pedidos y Reparto",
        startup_mode=StartupMode.LAZY,
        routes=(ORDERS_DELIVERY_ROUTE_ID,),
        permissions=frozenset({ORDERS_DELIVERY_REQUIRED_PERMISSION}),
    )


def build_orders_delivery_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=ORDERS_DELIVERY_ROUTE_ID,
        module_id=ORDERS_DELIVERY_MODULE_ID,
        title="Pedidos y Reparto",
        view_factory_id=ORDERS_DELIVERY_VIEW_FACTORY_ID,
        breadcrumb=("Pedidos y Reparto",),
        required_permission=ORDERS_DELIVERY_REQUIRED_PERMISSION,
    )


class OrdersDeliveryModuleActivator:
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
        from frontend.desktop.modules.orders_delivery.orders_delivery_view import (
            OrdersDeliveryView,
        )

        session = self._session_context
        return OrdersDeliveryView(
            has_permission=self._has_permission,
            connection=self._connection,
            branch_id=getattr(session, "sucursal_id", None) or getattr(session, "branch_id", None),
            actor_user_id=getattr(session, "user_id", None),
        )


    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(ORDERS_DELIVERY_VIEW_FACTORY_ID, self._build_view)

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
from frontend.desktop.shell.modules.session_access import (
    active_branch_id,
    actor_user_id,
    sidebar_permission_checker,
)
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

    def _build_view(self):
        """La vista arma su propio `page_builder` a partir de
        `connection`/`branch_id`/`actor_user_id` (ORD-28), así que aquí NO se
        recompone nada: sólo se lee la sesión.

        Esa lectura vivía copiada en este archivo y traía un error: el
        `_has_permission` local sondeaba `has_permission`/`permissions`,
        atributos que ni `SessionContext` ni `LegacySessionAdapter` definen
        —ambos hablan `tiene_permiso`/`permisos`—, así que devolvía False
        siempre y el sidebar interno salía VACÍO. Ahora la derivación es la
        compartida del shell, con una sola implementación (§26).
        """
        from frontend.desktop.modules.orders_delivery.orders_delivery_view import (
            OrdersDeliveryView,
        )

        session = self._session_context
        return OrdersDeliveryView(
            has_permission=sidebar_permission_checker(session),
            connection=self._connection,
            branch_id=active_branch_id(session),
            actor_user_id=actor_user_id(session),
        )


    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(ORDERS_DELIVERY_VIEW_FACTORY_ID, self._build_view)

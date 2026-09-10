"""Purchasing registration into the new shell — SHELL-16.

Module 7 of the module-by-module migration off the legacy application-wide
dependency container (modules 1-6: `sales_pos`, `customers_crm`, `finance`,
`hr`, `inventory`, `products` — see
`frontend/desktop/modules/sales_pos/shell_registration.py` for the
template this mirrors). Same shape as `finance`/`hr`: `enterprise_routes.py`'s
own `create_enterprise_purchasing_view(container, parent=None)` still
takes that container directly, but the lower-level `build_enterprise_presenter(connection,
session_context=None, *, logistics_service=None, logistics_queries=None)`
and `direct_purchase_routes.py::build_direct_purchase_presenter(connection,
session_context=None)` it composes are already fully explicit-dependency
— so this file bypasses `create_enterprise_purchasing_view` entirely and
replicates its (already container-free) composition directly, the same
way `modulos/compras_enterprise.py` never had to.

`logistics_service`/`logistics_queries` are accepted as optional explicit
values too — in production they come from the canonical Logistics wiring
built once at app startup (`core/events/wiring.py::_wire_logistics_pipeline`),
never reconstructed here, exactly matching what the legacy factory does.

Deliberately **not** wired into `main.py`/`MainWindow`/`MenuLateral` this
round, matching every prior module's own scope boundary.
`modulos/compras_enterprise.py` remains the live bridge for now.
"""
from __future__ import annotations

from typing import Optional

from backend.security.permissions.codes import permission_code
from frontend.desktop.modules.purchasing.direct_purchase_routes import build_direct_purchase_presenter
from frontend.desktop.modules.purchasing.direct_purchase_view import (
    DirectPurchaseCreateView,
    DirectPurchaseHistoryView,
)
from frontend.desktop.modules.purchasing.enterprise_routes import build_enterprise_presenter
from frontend.desktop.modules.purchasing.enterprise_view import EnterprisePurchasingView
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

PURCHASING_MODULE_ID = "purchasing"
PURCHASING_ROUTE_ID = "purchasing.workspace"
PURCHASING_VIEW_FACTORY_ID = "purchasing.workspace_view"

# The real, existing catalog code (`core/security/permission_catalog.py`)
# — not a new permission invented for this migration.
PURCHASING_REQUIRED_PERMISSION = permission_code("COMPRAS", "ver")


def build_purchasing_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=PURCHASING_MODULE_ID,
        display_name="Compras",
        startup_mode=StartupMode.LAZY,
        routes=(PURCHASING_ROUTE_ID,),
        permissions=frozenset({PURCHASING_REQUIRED_PERMISSION}),
    )


def build_purchasing_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=PURCHASING_ROUTE_ID,
        module_id=PURCHASING_MODULE_ID,
        title="Compras",
        view_factory_id=PURCHASING_VIEW_FACTORY_ID,
        breadcrumb=("Compras",),
        required_permission=PURCHASING_REQUIRED_PERMISSION,
    )


def create_purchasing_view(
    connection, session_context=None, *,
    logistics_service=None, logistics_queries=None, parent=None,
):
    """Explicit-dependency equivalent of `enterprise_routes.py::create_enterprise_purchasing_view`
    — never receives a container, only what it needs, already unwrapped."""
    presenter = build_enterprise_presenter(
        connection, session_context,
        logistics_service=logistics_service, logistics_queries=logistics_queries)
    direct_presenter = build_direct_purchase_presenter(connection, session_context)
    direct_views = {
        "create": DirectPurchaseCreateView(direct_presenter),
        "history": DirectPurchaseHistoryView(direct_presenter),
    }
    return EnterprisePurchasingView(presenter, parent, direct_purchase_views=direct_views)


class PurchasingModuleActivator:
    """A `ModuleActivator` (SHELL-13) — structural, not inherited, same
    convention every activator/service test double in this codebase
    already follows. Registers `purchasing`'s real view factory into a
    live `ViewFactoryRegistry`, given only the same explicit values
    `create_purchasing_view` already takes today — never the whole
    dependency bundle `enterprise_routes.py::create_enterprise_purchasing_view`
    still accepts at its own boundary."""

    def __init__(
        self, *, connection, view_factory_registry, session_context: Optional[object] = None,
        logistics_service: Optional[object] = None, logistics_queries: Optional[object] = None,
    ) -> None:
        self._connection = connection
        self._session_context = session_context
        self._logistics_service = logistics_service
        self._logistics_queries = logistics_queries
        self._view_factories = view_factory_registry

    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(
            PURCHASING_VIEW_FACTORY_ID,
            lambda: create_purchasing_view(
                self._connection, self._session_context,
                logistics_service=self._logistics_service, logistics_queries=self._logistics_queries,
            ),
        )

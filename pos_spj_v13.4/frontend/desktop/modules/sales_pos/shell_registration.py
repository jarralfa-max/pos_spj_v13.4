"""Sales/POS registration into the new shell — SHELL-16.

The first module migrated off the legacy application-wide dependency
container under the SHELL-8..15 shell architecture. `frontend/desktop/modules/sales_pos/composition.py`
was *already* explicit-dependency (`connection`, `session_context`,
`printer_service` — never that container) since POS-19; the only piece
that still touched it was the one-file bridge `modulos/ventas_pos.py`,
which unwraps it via `getattr(container, "db", ...)` before ever calling
into this package. This file is the shell-side counterpart: a
`ModuleDescriptor`, a `RouteDefinition`, and a `SalesPosModuleActivator`
(a `ModuleActivator`, SHELL-13) that takes those same three explicit
values — never a whole dependency container — and registers the real
view factory.

Deliberately **not** wired into `main.py`/`MainWindow`/`MenuLateral` this
round (matching every prior SHELL phase's discipline: build and prove it
standalone first). `modulos/ventas_pos.py` remains the live bridge for now
— swapping the legacy shell over to construct+navigate through this
registration instead is separate, higher-blast-radius work for a later,
explicitly-scoped round.
"""
from __future__ import annotations

from typing import Optional

from backend.security.permissions.codes import permission_code
from frontend.desktop.modules.sales_pos.composition import create_sales_pos_view
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

SALES_POS_MODULE_ID = "sales_pos"
SALES_POS_ROUTE_ID = "sales_pos.workspace"
SALES_POS_VIEW_FACTORY_ID = "sales_pos.workspace_view"

# The real, existing catalog code (`core/security/permission_catalog.py`) —
# not a new permission invented for this migration. The legacy screen is
# reached today gated on this same "POS" module/"ver" action pair.
SALES_POS_REQUIRED_PERMISSION = permission_code("POS", "ver")


def build_sales_pos_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=SALES_POS_MODULE_ID,
        display_name="Punto de Venta",
        startup_mode=StartupMode.LAZY,
        routes=(SALES_POS_ROUTE_ID,),
        permissions=frozenset({SALES_POS_REQUIRED_PERMISSION}),
    )


def build_sales_pos_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=SALES_POS_ROUTE_ID,
        module_id=SALES_POS_MODULE_ID,
        title="Punto de Venta",
        view_factory_id=SALES_POS_VIEW_FACTORY_ID,
        breadcrumb=("Ventas", "Punto de Venta"),
        required_permission=SALES_POS_REQUIRED_PERMISSION,
    )


class SalesPosModuleActivator:
    """A `ModuleActivator` (SHELL-13) — structural, not inherited, same
    convention every activator/service test double in this codebase
    already follows. Registers `sales_pos`'s real view factory into a live
    `ViewFactoryRegistry`, given only the same three explicit values
    `modulos/ventas_pos.py` already unwraps today — `connection` is
    required (there is no sensible POS screen without one); `session_context`/
    `printer_service` are optional, matching `create_sales_pos_view()`'s own
    defaults."""

    def __init__(
        self, *, connection, view_factory_registry,
        session_context: Optional[object] = None, printer_service: Optional[object] = None,
    ) -> None:
        self._connection = connection
        self._session_context = session_context
        self._printer_service = printer_service
        self._view_factories = view_factory_registry

    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(
            SALES_POS_VIEW_FACTORY_ID,
            lambda: create_sales_pos_view(self._connection, self._session_context, self._printer_service),
        )

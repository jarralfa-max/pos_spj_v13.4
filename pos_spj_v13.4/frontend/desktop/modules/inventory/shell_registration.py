"""Inventory registration into the new shell — SHELL-16.

Module 5 of the module-by-module migration off the legacy application-wide
dependency container (modules 1-4: `sales_pos`, `customers_crm`, `finance`,
`hr` — see `frontend/desktop/modules/sales_pos/shell_registration.py` for
the template this mirrors). Unlike those four, `inventory`'s composition
logic didn't already live in a separable, container-free function — it
was embedded directly inside the legacy `modulos/inventario_enterprise.py`
host class. This phase's own extraction
(`frontend/desktop/modules/inventory/composition.py::build_inventory_presenter`/
`create_inventory_view`) came first, behavior-preserved and verified
against the pre-existing regression tests in
`tests/integration/inventory/test_inventory_enterprise_session_wiring.py`
— this file is the SHELL-16 registration built on top of that new,
already-explicit composition root, same as modules 1-4.

Deliberately **not** wired into `main.py`/`MainWindow`/`MenuLateral` this
round, matching modules 1-4's own scope boundary. `modulos/inventario_enterprise.py`
remains the live bridge for now (now itself calling the extracted
composition root instead of doing the wiring inline).
"""
from __future__ import annotations

from typing import Optional

from core.security.permission_catalog import permission_code
from frontend.desktop.modules.inventory.composition import create_inventory_view
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

INVENTORY_MODULE_ID = "inventory"
INVENTORY_ROUTE_ID = "inventory.workspace"
INVENTORY_VIEW_FACTORY_ID = "inventory.workspace_view"

# The real, existing catalog code (`core/security/permission_catalog.py`)
# — not a new permission invented for this migration.
INVENTORY_REQUIRED_PERMISSION = permission_code("INVENTARIO", "ver")


def build_inventory_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=INVENTORY_MODULE_ID,
        display_name="Inventario",
        startup_mode=StartupMode.LAZY,
        routes=(INVENTORY_ROUTE_ID,),
        permissions=frozenset({INVENTORY_REQUIRED_PERMISSION}),
    )


def build_inventory_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=INVENTORY_ROUTE_ID,
        module_id=INVENTORY_MODULE_ID,
        title="Inventario",
        view_factory_id=INVENTORY_VIEW_FACTORY_ID,
        breadcrumb=("Inventario",),
        required_permission=INVENTORY_REQUIRED_PERMISSION,
    )


class InventoryModuleActivator:
    """A `ModuleActivator` (SHELL-13) — structural, not inherited, same
    convention every activator/service test double in this codebase
    already follows. Registers `inventory`'s real view factory into a live
    `ViewFactoryRegistry`, given only the same two explicit values
    `create_inventory_view` already takes today — never the whole
    dependency bundle `modulos/inventario_enterprise.py` still accepts at
    its own boundary."""

    def __init__(
        self, *, connection, view_factory_registry, session_context: Optional[object] = None,
    ) -> None:
        self._connection = connection
        self._session_context = session_context
        self._view_factories = view_factory_registry

    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(
            INVENTORY_VIEW_FACTORY_ID,
            lambda: create_inventory_view(self._connection, self._session_context),
        )

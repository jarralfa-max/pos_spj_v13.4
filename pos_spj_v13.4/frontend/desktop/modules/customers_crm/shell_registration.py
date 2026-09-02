"""Clientes/CRM registration into the new shell — SHELL-16.

Module 2 of the module-by-module migration off the legacy application-wide
dependency container (module 1 was `sales_pos` — see
`frontend/desktop/modules/sales_pos/shell_registration.py` for the
template this mirrors). `frontend/desktop/modules/customers_crm/composition.py`
was *already* explicit-dependency (`connection`, `session_context` — never
that container) under its own CRM-1 guardrail
(`tests/architecture/test_customers_crm_ui_does_not_receive_app_container.py`),
which this file's own source must also keep satisfying — the only piece
that still touched the container was the one-file bridge
`modulos/clientes_crm.py`, which unwraps it before ever calling into this
package. This file is the shell-side counterpart: a `ModuleDescriptor`, a
`RouteDefinition`, and a `CustomersCrmModuleActivator` (a `ModuleActivator`,
SHELL-13) that takes those same two explicit values — never a whole
dependency container — and registers the real view factory.

Deliberately **not** wired into `main.py`/`MainWindow`/`MenuLateral` this
round, matching module 1's own scope boundary. `modulos/clientes_crm.py`
remains the live bridge for now.
"""
from __future__ import annotations

from typing import Optional

from core.security.permission_catalog import permission_code
from frontend.desktop.modules.customers_crm.composition import create_customers_crm_view
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

CUSTOMERS_CRM_MODULE_ID = "customers_crm"
CUSTOMERS_CRM_ROUTE_ID = "customers_crm.workspace"
CUSTOMERS_CRM_VIEW_FACTORY_ID = "customers_crm.workspace_view"

# The real, existing catalog entry (`core/security/permission_catalog.py`)
# — its own comment there says it's "solo la puerta de entrada al menú
# lateral" for this exact module, distinct from the granular CLIENTES.*/
# CRM.* permissions the module uses internally.
CUSTOMERS_CRM_REQUIRED_PERMISSION = permission_code("CLIENTES_CRM", "ver")


def build_customers_crm_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=CUSTOMERS_CRM_MODULE_ID,
        display_name="Clientes y CRM",
        startup_mode=StartupMode.LAZY,
        routes=(CUSTOMERS_CRM_ROUTE_ID,),
        permissions=frozenset({CUSTOMERS_CRM_REQUIRED_PERMISSION}),
    )


def build_customers_crm_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=CUSTOMERS_CRM_ROUTE_ID,
        module_id=CUSTOMERS_CRM_MODULE_ID,
        title="Clientes y CRM",
        view_factory_id=CUSTOMERS_CRM_VIEW_FACTORY_ID,
        breadcrumb=("Clientes", "Clientes y CRM"),
        required_permission=CUSTOMERS_CRM_REQUIRED_PERMISSION,
    )


class CustomersCrmModuleActivator:
    """A `ModuleActivator` (SHELL-13) — structural, not inherited, same
    convention every activator/service test double in this codebase
    already follows. Registers `customers_crm`'s real view factory into a
    live `ViewFactoryRegistry`, given only the same two explicit values
    `modulos/clientes_crm.py` already unwraps today."""

    def __init__(
        self, *, connection, view_factory_registry, session_context: Optional[object] = None,
    ) -> None:
        self._connection = connection
        self._session_context = session_context
        self._view_factories = view_factory_registry

    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(
            CUSTOMERS_CRM_VIEW_FACTORY_ID,
            lambda: create_customers_crm_view(self._connection, self._session_context),
        )

"""Finance registration into the new shell — SHELL-16.

Module 3 of the module-by-module migration off the legacy application-wide
dependency container (modules 1-2: `sales_pos`, `customers_crm` — see
`frontend/desktop/modules/sales_pos/shell_registration.py` for the
template this mirrors). Unlike those two, `finance_routes.py`'s own
`create_finance_view(container, parent=None)` still takes that container
directly (it has no dedicated "never receives it" guardrail the way
sales_pos/customers_crm do) — but the lower-level `build_finance_presenter(connection,
session_context=None)` it calls internally is already fully
explicit-dependency, so this file bypasses `create_finance_view` entirely
and calls `build_finance_presenter` + `FinanceView` directly, the same way
`modulos/finanzas.py` never had to for the other two modules. This file's
own source is still scanned by `tests/architecture/test_finance_bounded_context.py`'s
UI-wide checks (no SQL, no db connections, no repositories, no legacy
container) — `finance_routes.py` is the one file that guardrail
allowlists for that; this one isn't, and doesn't need to be.

Deliberately **not** wired into `main.py`/`MainWindow`/`MenuLateral` this
round, matching modules 1-2's own scope boundary. `modulos/finanzas.py`
remains the live bridge for now.
"""
from __future__ import annotations

from typing import Optional

from core.security.permission_catalog import permission_code
from frontend.desktop.modules.finance.finance_routes import build_finance_presenter
from frontend.desktop.modules.finance.finance_view import FinanceView
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

FINANCE_MODULE_ID = "finance"
FINANCE_ROUTE_ID = "finance.workspace"
FINANCE_VIEW_FACTORY_ID = "finance.workspace_view"

# The real, existing catalog code (`core/security/permission_catalog.py`)
# — not a new permission invented for this migration.
FINANCE_REQUIRED_PERMISSION = permission_code("FINANZAS", "ver")


def build_finance_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=FINANCE_MODULE_ID,
        display_name="Finanzas",
        startup_mode=StartupMode.LAZY,
        routes=(FINANCE_ROUTE_ID,),
        permissions=frozenset({FINANCE_REQUIRED_PERMISSION}),
    )


def build_finance_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=FINANCE_ROUTE_ID,
        module_id=FINANCE_MODULE_ID,
        title="Finanzas",
        view_factory_id=FINANCE_VIEW_FACTORY_ID,
        breadcrumb=("Finanzas",),
        required_permission=FINANCE_REQUIRED_PERMISSION,
    )


class FinanceModuleActivator:
    """A `ModuleActivator` (SHELL-13) — structural, not inherited, same
    convention every activator/service test double in this codebase
    already follows. Registers `finance`'s real view factory into a live
    `ViewFactoryRegistry`, given only the same two explicit values
    `build_finance_presenter` already takes today — never the whole
    dependency bundle `finance_routes.py::create_finance_view` still
    accepts."""

    def __init__(
        self, *, connection, view_factory_registry, session_context: Optional[object] = None,
    ) -> None:
        self._connection = connection
        self._session_context = session_context
        self._view_factories = view_factory_registry

    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(
            FINANCE_VIEW_FACTORY_ID,
            lambda: FinanceView(build_finance_presenter(self._connection, self._session_context)),
        )

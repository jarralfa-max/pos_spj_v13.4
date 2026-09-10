"""HR registration into the new shell — SHELL-16.

Module 4 of the module-by-module migration off the legacy application-wide
dependency container (modules 1-3: `sales_pos`, `customers_crm`, `finance`
— see `frontend/desktop/modules/sales_pos/shell_registration.py` for the
template this mirrors). Same shape as `finance`: `hr_routes.py`'s own
`create_hr_view(container, parent=None)` still takes that container
directly, but the lower-level `build_hr_presenter(connection, session_context=None)`
it calls internally is already fully explicit-dependency, so this file
bypasses `create_hr_view` entirely and calls `build_hr_presenter` + `HRView`
directly.

Deliberately **not** wired into `main.py`/`MainWindow`/`MenuLateral` this
round, matching modules 1-3's own scope boundary. `modulos/rrhh.py`
remains the live bridge for now.
"""
from __future__ import annotations

from typing import Optional

from backend.security.permissions.codes import permission_code
from frontend.desktop.modules.hr.hr_routes import build_hr_presenter
from frontend.desktop.modules.hr.hr_view import HRView
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

HR_MODULE_ID = "hr"
HR_ROUTE_ID = "hr.workspace"
HR_VIEW_FACTORY_ID = "hr.workspace_view"

# The real, existing catalog code (`core/security/permission_catalog.py`)
# — not a new permission invented for this migration.
HR_REQUIRED_PERMISSION = permission_code("RRHH", "ver")


def build_hr_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=HR_MODULE_ID,
        display_name="Recursos Humanos",
        startup_mode=StartupMode.LAZY,
        routes=(HR_ROUTE_ID,),
        permissions=frozenset({HR_REQUIRED_PERMISSION}),
    )


def build_hr_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=HR_ROUTE_ID,
        module_id=HR_MODULE_ID,
        title="Recursos Humanos",
        view_factory_id=HR_VIEW_FACTORY_ID,
        breadcrumb=("Recursos Humanos",),
        required_permission=HR_REQUIRED_PERMISSION,
    )


class HRModuleActivator:
    """A `ModuleActivator` (SHELL-13) — structural, not inherited, same
    convention every activator/service test double in this codebase
    already follows. Registers `hr`'s real view factory into a live
    `ViewFactoryRegistry`, given only the same two explicit values
    `build_hr_presenter` already takes today — never the whole dependency
    bundle `hr_routes.py::create_hr_view` still accepts."""

    def __init__(
        self, *, connection, view_factory_registry, session_context: Optional[object] = None,
    ) -> None:
        self._connection = connection
        self._session_context = session_context
        self._view_factories = view_factory_registry

    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(
            HR_VIEW_FACTORY_ID,
            lambda: HRView(build_hr_presenter(self._connection, self._session_context)),
        )

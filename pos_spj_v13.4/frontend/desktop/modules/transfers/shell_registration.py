"""Transfers (Transferencias) registration into the new shell — SHELL-16.

Module 9 of the module-by-module migration off the legacy application-wide
dependency container (modules 1-8: `sales_pos`, `customers_crm`, `finance`,
`hr`, `inventory`, `products`, `purchasing`, `cash_register` — see
`frontend/desktop/modules/sales_pos/shell_registration.py` for the
template this mirrors). Same shape as `finance`/`hr`/`purchasing`:
`backend/infrastructure/desktop/transfers_factory.py::TransfersModuleHost`
still takes a container directly, but everything it composes underneath —
`TransferUseCaseFactory.from_session(session, connection=...)` (or
`.for_tests(connection=...)` with no session) and
`TransfersPresenter(query, connection=..., create_transfer_request_uc=...,
session_context=...)` — is already fully explicit-dependency. This file
bypasses `TransfersModuleHost` entirely and replicates its (already
container-free) composition directly, the same way `purchasing` bypasses
`create_enterprise_purchasing_view`.

This module's UI directory (`frontend/desktop/modules/transfers/`) is
guarded by `tests/architecture/test_transfers_ui_uses_design_system.py`
against importing repositories directly, so — unlike this file's
counterpart in every other module — the explicit-dependency composition
function itself (`create_transfers_view`) is NOT redefined here; it's
imported from `backend/infrastructure/desktop/transfers_factory.py`,
where it now lives alongside the (still container-consuming, still
unmodified in behavior) `TransfersModuleHost` it was extracted from.

Deliberately **not** wired into `main.py`/`MainWindow`/`MenuLateral` this
round, matching every prior module's own scope boundary.
`TransfersModuleHost` (wired via `core/ui/module_loader.py` and
`interfaz/main_window.py`) remains the live construction path for now.
"""
from __future__ import annotations

from typing import Optional

from backend.infrastructure.desktop.transfers_factory import create_transfers_view
from backend.security.permissions.codes import permission_code
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

TRANSFERS_MODULE_ID = "transfers"
TRANSFERS_ROUTE_ID = "transfers.workspace"
TRANSFERS_VIEW_FACTORY_ID = "transfers.workspace_view"

# The real, existing catalog code (`core/security/permission_catalog.py`)
# — not a new permission invented for this migration.
TRANSFERS_REQUIRED_PERMISSION = permission_code("TRANSFERENCIAS", "ver")


def build_transfers_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=TRANSFERS_MODULE_ID,
        display_name="Transferencias",
        startup_mode=StartupMode.LAZY,
        routes=(TRANSFERS_ROUTE_ID,),
        permissions=frozenset({TRANSFERS_REQUIRED_PERMISSION}),
    )


def build_transfers_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=TRANSFERS_ROUTE_ID,
        module_id=TRANSFERS_MODULE_ID,
        title="Transferencias",
        view_factory_id=TRANSFERS_VIEW_FACTORY_ID,
        breadcrumb=("Transferencias",),
        required_permission=TRANSFERS_REQUIRED_PERMISSION,
    )


class TransfersModuleActivator:
    """A `ModuleActivator` (SHELL-13) — structural, not inherited, same
    convention every activator/service test double in this codebase
    already follows. Registers `transfers`'s real view factory into a
    live `ViewFactoryRegistry`, given only the same explicit values
    `create_transfers_view` already takes — never the whole dependency
    bundle `TransfersModuleHost` still accepts at its own boundary."""

    def __init__(
        self, *, connection, view_factory_registry, session_context: Optional[object] = None,
    ) -> None:
        self._connection = connection
        self._session_context = session_context
        self._view_factories = view_factory_registry

    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(
            TRANSFERS_VIEW_FACTORY_ID,
            lambda: create_transfers_view(self._connection, self._session_context),
        )

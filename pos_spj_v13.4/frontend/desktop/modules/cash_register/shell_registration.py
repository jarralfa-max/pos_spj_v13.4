"""Cash register (Caja) registration into the new shell — SHELL-16.

Module 8 of the module-by-module migration off the legacy application-wide
dependency container (modules 1-7: `sales_pos`, `customers_crm`, `finance`,
`hr`, `inventory`, `products`, `purchasing` — see
`frontend/desktop/modules/sales_pos/shell_registration.py` for the
template this mirrors). This module is architecturally different from all
seven before it: `backend/infrastructure/desktop/cash_register_factory.py::build_cash_register_presenter`
reads and writes a *composition-root-shaped* object throughout its ~1000
lines — not just to unwrap a connection/session once at the top, but as
an ongoing, deliberate design: ~15 optional service overrides via
`getattr(composition_root, name, None)` (reuse a canonical singleton wired
elsewhere if the container has one, else build fresh — the same pattern
`purchasing`'s `logistics_service`/`logistics_queries` use, just with many
more names), plus two genuine mutable cache slots
(`active_cash_shift_id`/`active_cash_count_id`, written via `setattr` and
read back both here and by `backend/infrastructure/desktop/cash_operational_context.py::DesktopCashOperationalContextResolver`,
which also takes the same object explicitly).

Rewriting that file to pure named parameters would be a large, higher-risk
change to a big, already-tested file, and would have to invent a new home
for the two cache slots. Instead: `build_cash_register_presenter()`/
`create_cash_register_view()` are used **unmodified** — this file's own
`CashRegisterModuleActivator` never receives or touches the real
container; it constructs `_CashRegisterCompositionStandIn` (a minimal,
purpose-built object exposing only `.db`/`.session` — nothing else) and
hands *that* to the existing factory. Every optional override defaults to
`None` via the factory's own `getattr(..., None)` fallbacks and builds
fresh internally, exactly like a production container with no explicit
overrides configured — the cache slots work correctly since the stand-in
is a real, mutable object with the lifetime of one view. This is exactly
the shape `tests/integration/cash_register/test_cash_register_factory_active_context.py`'s
own `class _Root: pass` + `.db`/`.session` already uses, confirming this
is the file's own established test-composition idiom, not a workaround
invented for this migration.

Deliberately **not** wired into `main.py`/`MainWindow`/`MenuLateral` this
round, matching every prior module's own scope boundary.
`backend/infrastructure/desktop/cash_register_factory.py::CashRegisterModuleHost`
remains the live construction path for now.
"""
from __future__ import annotations

from typing import Optional

from backend.infrastructure.desktop.cash_register_factory import create_cash_register_view
from core.security.permission_catalog import permission_code
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

CASH_REGISTER_MODULE_ID = "cash_register"
CASH_REGISTER_ROUTE_ID = "cash_register.workspace"
CASH_REGISTER_VIEW_FACTORY_ID = "cash_register.workspace_view"

# The real, existing catalog code (`core/security/permission_catalog.py`)
# — not a new permission invented for this migration.
CASH_REGISTER_REQUIRED_PERMISSION = permission_code("CAJA", "ver")


def build_cash_register_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=CASH_REGISTER_MODULE_ID,
        display_name="Caja",
        startup_mode=StartupMode.LAZY,
        routes=(CASH_REGISTER_ROUTE_ID,),
        permissions=frozenset({CASH_REGISTER_REQUIRED_PERMISSION}),
    )


def build_cash_register_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=CASH_REGISTER_ROUTE_ID,
        module_id=CASH_REGISTER_MODULE_ID,
        title="Caja",
        view_factory_id=CASH_REGISTER_VIEW_FACTORY_ID,
        breadcrumb=("Caja",),
        required_permission=CASH_REGISTER_REQUIRED_PERMISSION,
    )


class _CashRegisterCompositionStandIn:
    """Purpose-built substitute for the composition-root shape
    `cash_register_factory.py` expects — NOT the real application
    container, and never derived from or wrapping one. Only `.db`/`.session`
    are set; every other attribute the factory's `getattr(..., None)`
    calls look for is simply absent, so each one falls back to building a
    fresh, real service internally — the same behavior a production
    container with no explicit overrides configured would produce. The two
    cache slots (`active_cash_shift_id`/`active_cash_count_id`) the
    factory writes via `setattr` work correctly because this is a real,
    plain, mutable object with the lifetime of one constructed view."""

    def __init__(self, *, connection, session_context=None) -> None:
        self.db = connection
        self.session = session_context


class CashRegisterModuleActivator:
    """A `ModuleActivator` (SHELL-13) — structural, not inherited, same
    convention every activator/service test double in this codebase
    already follows. Never receives or references the real application
    container — only explicit `connection`/`session_context` — and builds
    the minimal stand-in the existing, unmodified factory needs."""

    def __init__(
        self, *, connection, view_factory_registry, session_context: Optional[object] = None,
    ) -> None:
        self._connection = connection
        self._session_context = session_context
        self._view_factories = view_factory_registry

    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(
            CASH_REGISTER_VIEW_FACTORY_ID,
            lambda: create_cash_register_view(_CashRegisterCompositionStandIn(
                connection=self._connection, session_context=self._session_context,
            )),
        )

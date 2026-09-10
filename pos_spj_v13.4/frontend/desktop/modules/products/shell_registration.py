"""Products registration into the new shell — SHELL-16.

Module 6 of the module-by-module migration off the legacy application-wide
dependency container (modules 1-5: `sales_pos`, `customers_crm`, `finance`,
`hr`, `inventory` — see `frontend/desktop/modules/sales_pos/shell_registration.py`
for the template this mirrors). Same shape as `inventory` (module 5):
`products`'s composition logic didn't already live in a separable,
container-free function — it was embedded directly inside the legacy
`modulos/productos_enterprise.py` host class, including a `_Session`
identity wrapper with a subtler two-track shape (a raw `live_session` used
for authorization, and a wrapped `_Session` used as `session_context` —
see `composition.py`'s own docstring). That extraction came first,
behavior-preserved and verified against the pre-existing regression tests
in `tests/integration/products/test_products_enterprise_host.py` — this
file is the SHELL-16 registration built on top of that new,
already-explicit composition root, same as every module before it.

Deliberately **not** wired into `main.py`/`MainWindow`/`MenuLateral` this
round, matching prior modules' own scope boundary. `modulos/productos_enterprise.py`
remains the live bridge for now (now itself calling the extracted
composition root instead of doing the wiring inline).
"""
from __future__ import annotations

from typing import Optional

from backend.security.permissions.codes import permission_code
from frontend.desktop.modules.products.composition import _Session, create_products_view
from frontend.desktop.shell.modules.module_descriptor import ModuleDescriptor
from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.route_definition import RouteDefinition

PRODUCTS_MODULE_ID = "products"
PRODUCTS_ROUTE_ID = "products.workspace"
PRODUCTS_VIEW_FACTORY_ID = "products.workspace_view"

# The real, existing catalog code (`core/security/permission_catalog.py`)
# — not a new permission invented for this migration.
PRODUCTS_REQUIRED_PERMISSION = permission_code("PRODUCTOS", "ver")


def build_products_module_descriptor() -> ModuleDescriptor:
    return ModuleDescriptor(
        module_id=PRODUCTS_MODULE_ID,
        display_name="Productos",
        startup_mode=StartupMode.LAZY,
        routes=(PRODUCTS_ROUTE_ID,),
        permissions=frozenset({PRODUCTS_REQUIRED_PERMISSION}),
    )


def build_products_route_definition() -> RouteDefinition:
    return RouteDefinition(
        route_id=PRODUCTS_ROUTE_ID,
        module_id=PRODUCTS_MODULE_ID,
        title="Productos",
        view_factory_id=PRODUCTS_VIEW_FACTORY_ID,
        breadcrumb=("Productos",),
        required_permission=PRODUCTS_REQUIRED_PERMISSION,
    )


class ProductsModuleActivator:
    """A `ModuleActivator` (SHELL-13) — structural, not inherited, same
    convention every activator/service test double in this codebase
    already follows. Registers `products`'s real view factory into a live
    `ViewFactoryRegistry`, given only the same explicit values
    `create_products_view` already takes today — never the whole
    dependency bundle `modulos/productos_enterprise.py` still accepts at
    its own boundary.

    `live_session` and `branch_id_fallback` are accepted separately
    (rather than a single already-built `_Session`) so this activator
    itself never has to import or know about `_Session`'s existence —
    `create_products_view` builds it internally, exactly matching how the
    legacy bridge builds its own equivalent for `self._session`."""

    def __init__(
        self, *, connection, view_factory_registry,
        live_session: Optional[object] = None, branch_id_fallback: Optional[str] = None,
    ) -> None:
        self._connection = connection
        self._live_session = live_session
        self._branch_id_fallback = branch_id_fallback
        self._view_factories = view_factory_registry

    def activate(self, module: ModuleDescriptor) -> None:
        self._view_factories.register(
            PRODUCTS_VIEW_FACTORY_ID,
            lambda: create_products_view(
                self._connection, _Session(self._live_session, self._branch_id_fallback),
                live_session=self._live_session,
            ),
        )

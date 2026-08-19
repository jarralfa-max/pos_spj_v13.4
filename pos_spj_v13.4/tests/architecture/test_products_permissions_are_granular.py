"""§38 re-audit (2026-08-18) — Products uses granular, catalog-registered
permissions only.

Every sensitive Products action is gated by its own granular `PRODUCTOS.accion`
permission (the app-wide canonical `MODULO.accion` format, see
`core/security/permission_catalog.py`), validated in the backend; a single
broad "PRODUCTOS.editar" gating every action must never exist.

Before this test existed, `ProductPermissions.*` held 68 flat, unregistered
English codes (`PRODUCTS_VIEW`, ...) with zero entries in
`CANONICAL_MODULE_PERMISSIONS["PRODUCTOS"]` — no admin could ever grant them
distinctly through the real permission matrix, and the whole granular
vocabulary was decorative (every check silently fell back to one of 4 coarse
legacy codes via `permission_bridge.py`). Fixed by switching every value to
the dotted `PRODUCTOS.accion` convention and registering all of them in the
catalog. Unlike Inventory (INV-1, fully cut over), Products still keeps
`permission_bridge.py`'s legacy fallback intentionally (roles seeded only with
`PRODUCTOS.ver/crear/editar/eliminar` must not lose access) — so this file
does NOT assert the bridge is gone, only that the granular vocabulary is real
and catalog-backed.
"""

from __future__ import annotations

from backend.application.products.permissions import (
    ALL_PRODUCT_PERMISSIONS,
    ProductPermissions,
)
from core.security.permission_catalog import (
    CANONICAL_MODULE_PERMISSIONS,
    permission_code,
)


def test_products_permissions_are_granular():
    assert len(ALL_PRODUCT_PERMISSIONS) >= 60
    # representative sample of the granular vocabulary
    for code in (
        ProductPermissions.RECIPE_APPROVE,
        ProductPermissions.YIELD_ACTIVATE,
        ProductPermissions.MEAT_CLASSIFICATION_MANAGE,
        ProductPermissions.INTERNAL_CREATE,
        ProductPermissions.EXTERNAL_APPROVE,
        ProductPermissions.CUTTING_SCHEME_MANAGE,
        ProductPermissions.IMPORT_APPROVE,
    ):
        assert code in ALL_PRODUCT_PERMISSIONS


def test_no_flat_unregistered_product_codes_reachable():
    # The pre-fix vocabulary (`PRODUCTS_VIEW`, ...) must never come back.
    for code in ALL_PRODUCT_PERMISSIONS:
        assert not code.startswith("PRODUCTS_"), code


def test_all_product_permission_values_use_module_action_format():
    for name, value in vars(ProductPermissions).items():
        if name.startswith("_") or not isinstance(value, str):
            continue
        assert value.startswith("PRODUCTOS."), f"{name}={value}"
        assert value == value.strip()
        action = value.split(".", 1)[1]
        assert action == action.lower(), f"{name}={value} (acción debe ser minúscula)"


def test_catalog_and_enum_are_in_lockstep():
    catalog_codes = {
        permission_code("PRODUCTOS", action)
        for action in CANONICAL_MODULE_PERMISSIONS["PRODUCTOS"]
    }
    enum_codes = set(ALL_PRODUCT_PERMISSIONS)
    assert enum_codes == catalog_codes, (
        f"En el catálogo pero no en el enum: {catalog_codes - enum_codes}\n"
        "En el enum pero no en el catálogo (nunca podrá otorgarse vía la UI real): "
        f"{enum_codes - catalog_codes}")

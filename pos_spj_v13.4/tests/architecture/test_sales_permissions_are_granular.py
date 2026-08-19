"""SALES-2 (master prompt §61, §64) — the Sales/POS context uses granular
permissions only, and every one of them is registered in the app-wide
CANONICAL_MODULE_PERMISSIONS catalog under the existing "POS" key (reused,
not a parallel "VENTAS" key — one canonical route per functional area,
§3/§64)."""

from __future__ import annotations

from backend.application.sales.permissions import ALL_SALES_PERMISSIONS, SalesPermissions
from core.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS


def test_sales_permissions_are_granular():
    assert len(ALL_SALES_PERMISSIONS) >= 25
    for code in (
        SalesPermissions.SALE_CANCEL,
        SalesPermissions.SALE_SUSPEND,
        SalesPermissions.RETURN,
        SalesPermissions.REVERSE,
        SalesPermissions.DISCOUNT_OVERRIDE,
        SalesPermissions.PRICE_OVERRIDE,
        SalesPermissions.DRAWER_OPEN_MANUAL,
        SalesPermissions.PAYMENT_CREDIT,
    ):
        assert code in ALL_SALES_PERMISSIONS


def test_every_permission_is_pos_prefixed_string():
    for code in ALL_SALES_PERMISSIONS:
        assert isinstance(code, str) and code.startswith("POS.")


def test_no_duplicate_codes():
    values = list(vars(SalesPermissions).values())
    codes = [v for v in values if isinstance(v, str)]
    assert len(codes) == len(set(codes))


def test_every_sales_permission_registered_in_pos_catalog_key():
    """Reuses the existing "POS" key (does not mint a parallel "VENTAS" key)
    — every SalesPermissions code, minus its "POS." prefix, must appear in
    CANONICAL_MODULE_PERMISSIONS["POS"] so it surfaces in the real
    Configuración → Seguridad → Permisos matrix."""
    registered = set(CANONICAL_MODULE_PERMISSIONS["POS"])
    for code in ALL_SALES_PERMISSIONS:
        suffix = code.split(".", 1)[1]
        assert suffix in registered, f"{code} not registered under POS in permission_catalog.py"


def test_no_venta_parallel_module_key_was_created():
    assert "VENTAS" not in CANONICAL_MODULE_PERMISSIONS

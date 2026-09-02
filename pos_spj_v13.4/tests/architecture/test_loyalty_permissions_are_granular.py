"""LOY-1 (master prompt §59, §64) — the Fidelidad/Loyalty context uses
granular permissions only, and every one of them is registered in the
app-wide CANONICAL_MODULE_PERMISSIONS catalog under the existing
"GROWTH_ENGINE" key (reused, not a parallel "FIDELIDAD" key — one canonical
route per functional area, §3/§64)."""

from __future__ import annotations

from backend.application.loyalty.permissions import ALL_LOYALTY_PERMISSIONS, LoyaltyPermissions
from core.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS


def test_loyalty_permissions_are_granular():
    assert len(ALL_LOYALTY_PERMISSIONS) >= 40
    for code in (
        LoyaltyPermissions.POINTS_ADJUST,
        LoyaltyPermissions.POINTS_REVERSE,
        LoyaltyPermissions.COUPON_OVERRIDE,
        LoyaltyPermissions.VOUCHER_RELOAD,
        LoyaltyPermissions.SWEEPSTAKES_DRAW,
        LoyaltyPermissions.CAMPAIGN_ACTIVATE,
        LoyaltyPermissions.PROGRAM_APPROVE,
    ):
        assert code in ALL_LOYALTY_PERMISSIONS


def test_every_permission_is_growth_engine_prefixed_string():
    for code in ALL_LOYALTY_PERMISSIONS:
        assert isinstance(code, str) and code.startswith("GROWTH_ENGINE.")


def test_no_duplicate_codes():
    values = list(vars(LoyaltyPermissions).values())
    codes = [v for v in values if isinstance(v, str)]
    assert len(codes) == len(set(codes))


def test_every_loyalty_permission_registered_in_growth_engine_catalog_key():
    """Reuses the existing "GROWTH_ENGINE" key (does not mint a parallel
    "FIDELIDAD" key) — every LoyaltyPermissions code, minus its
    "GROWTH_ENGINE." prefix, must appear in
    CANONICAL_MODULE_PERMISSIONS["GROWTH_ENGINE"]."""
    registered = set(CANONICAL_MODULE_PERMISSIONS["GROWTH_ENGINE"])
    for code in ALL_LOYALTY_PERMISSIONS:
        suffix = code.split(".", 1)[1]
        assert suffix in registered, f"{code} not registered under GROWTH_ENGINE in permission_catalog.py"


def test_no_fidelidad_parallel_module_key_was_created():
    assert "FIDELIDAD" not in CANONICAL_MODULE_PERMISSIONS
    assert "LOYALTY" not in CANONICAL_MODULE_PERMISSIONS

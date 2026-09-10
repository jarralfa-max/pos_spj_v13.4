"""ORD-1 (master prompt §63, §64) — the Pedidos/Delivery context uses
granular permissions only, and every one of them is registered in the
app-wide CANONICAL_MODULE_PERMISSIONS catalog under the existing "DELIVERY"
key (reused, not a parallel "ORDERS"/"PEDIDOS" key — one canonical route per
functional area, §3/§64)."""

from __future__ import annotations

from backend.application.orders_delivery.permissions import (
    ALL_ORDERS_DELIVERY_PERMISSIONS,
    OrdersDeliveryPermissions,
)
from backend.application.security.permission_catalog import CANONICAL_MODULE_PERMISSIONS


def test_orders_delivery_permissions_are_granular():
    assert len(ALL_ORDERS_DELIVERY_PERMISSIONS) >= 40
    for code in (
        OrdersDeliveryPermissions.WEIGHT_OVERRIDE,
        OrdersDeliveryPermissions.DELIVERY_REVERSE,
        OrdersDeliveryPermissions.CASH_COLLECTION_OVERRIDE,
        OrdersDeliveryPermissions.SETTLEMENT_APPROVE,
        OrdersDeliveryPermissions.CUSTOMER_APPROVAL_OVERRIDE,
        OrdersDeliveryPermissions.ORDER_REVERSE,
    ):
        assert code in ALL_ORDERS_DELIVERY_PERMISSIONS


def test_every_permission_is_delivery_prefixed_string():
    for code in ALL_ORDERS_DELIVERY_PERMISSIONS:
        assert isinstance(code, str) and code.startswith("DELIVERY.")


def test_no_duplicate_codes():
    values = list(vars(OrdersDeliveryPermissions).values())
    codes = [v for v in values if isinstance(v, str)]
    assert len(codes) == len(set(codes))


def test_every_orders_delivery_permission_registered_in_delivery_catalog_key():
    """Reuses the existing "DELIVERY" key (does not mint a parallel
    "ORDERS"/"PEDIDOS" key) — every OrdersDeliveryPermissions code, minus its
    "DELIVERY." prefix, must appear in
    CANONICAL_MODULE_PERMISSIONS["DELIVERY"]."""
    registered = set(CANONICAL_MODULE_PERMISSIONS["DELIVERY"])
    for code in ALL_ORDERS_DELIVERY_PERMISSIONS:
        suffix = code.split(".", 1)[1]
        assert suffix in registered, f"{code} not registered under DELIVERY in permission_catalog.py"


def test_no_orders_or_pedidos_parallel_module_key_was_created():
    assert "ORDERS" not in CANONICAL_MODULE_PERMISSIONS
    assert "PEDIDOS" not in CANONICAL_MODULE_PERMISSIONS
    assert "ORDERS_DELIVERY" not in CANONICAL_MODULE_PERMISSIONS

"""Granular pricing / costing permission codes (PRC-1).

Pricing is never gated by a single ``PRECIOS`` permission. Viewing cost, changing a
sale price, approving/activating a price list, or overriding the minimum-price
protection each has its own code, re-validated by every use case (hiding a button
is not security). Segregation of duties (create ≠ approve) sits on top.
"""

from __future__ import annotations


class PricingPermissions:
    # ── consulta ──────────────────────────────────────────────────────────
    ACCESS = "PRICING_ACCESS"
    VIEW = "PRICING_VIEW"
    VIEW_COST = "PRICING_VIEW_COST"
    VIEW_MARGIN = "PRICING_VIEW_MARGIN"
    VIEW_AUDIT = "PRICING_VIEW_AUDIT"
    EXPORT = "PRICING_EXPORT"

    # ── precios de venta ──────────────────────────────────────────────────
    PRICE_CREATE = "PRICING_PRICE_CREATE"
    PRICE_EDIT = "PRICING_PRICE_EDIT"
    PRICE_MIN_OVERRIDE = "PRICING_PRICE_MIN_OVERRIDE"   # vender bajo el mínimo
    VOLUME_PRICE_MANAGE = "PRICING_VOLUME_PRICE_MANAGE"
    BRANCH_PRICE_MANAGE = "PRICING_BRANCH_PRICE_MANAGE"

    # ── listas de precio ──────────────────────────────────────────────────
    LIST_VIEW = "PRICING_LIST_VIEW"
    LIST_CREATE = "PRICING_LIST_CREATE"
    LIST_EDIT = "PRICING_LIST_EDIT"
    LIST_SUBMIT = "PRICING_LIST_SUBMIT"
    LIST_APPROVE = "PRICING_LIST_APPROVE"
    LIST_ACTIVATE = "PRICING_LIST_ACTIVATE"
    LIST_DEACTIVATE = "PRICING_LIST_DEACTIVATE"
    CUSTOMER_LIST_ASSIGN = "PRICING_CUSTOMER_LIST_ASSIGN"

    # ── costos ────────────────────────────────────────────────────────────
    COST_MANAGE = "PRICING_COST_MANAGE"
    COST_STANDARD_SET = "PRICING_COST_STANDARD_SET"

    # ── configuración ─────────────────────────────────────────────────────
    SETTINGS_VIEW = "PRICING_SETTINGS_VIEW"
    SETTINGS_MANAGE = "PRICING_SETTINGS_MANAGE"


ALL_PRICING_PERMISSIONS = frozenset(
    v for k, v in vars(PricingPermissions).items()
    if not k.startswith("_") and isinstance(v, str)
)


# Pares crea → aprueba/activa vigilados por la segregación de funciones.
SEGREGATED_APPROVALS = {
    PricingPermissions.LIST_APPROVE: PricingPermissions.LIST_CREATE,
    PricingPermissions.LIST_ACTIVATE: PricingPermissions.LIST_CREATE,
}

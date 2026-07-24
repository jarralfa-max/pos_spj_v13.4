"""Integration DTOs (§30-34) — the read contracts other contexts consume.

Every consumer (Inventory, Purchasing, POS/Sales, Quality) receives the product
master data it needs keyed by ``product_id``. Products never exposes stock balances
(Inventory) nor a final price (Pricing) — those fields are absent from these DTOs by
design, and guarded by ``test_product_master_does_not_store_stock`` /
``..._does_not_own_pricing``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InventoryProductConfigDTO:
    """What Inventory needs to manage a product (§30). No balances here."""

    product_id: str
    base_unit_id: str
    inventory_managed: bool
    lot_controlled: bool
    serial_controlled: bool
    expiration_controlled: bool
    catch_weight_enabled: bool
    quality_controlled: bool
    traceability_required: bool


@dataclass(frozen=True)
class PurchaseProductConfigDTO:
    """What Purchasing needs to buy a product (§31). No final price here."""

    product_id: str
    purchasable: bool
    base_unit_id: str
    is_meat: bool
    species_id: str | None
    catch_weight_enabled: bool
    requires_cold_chain: bool
    inspection_required: bool
    supplier_codes: tuple[str, ...]


@dataclass(frozen=True)
class PosProductDTO:
    """What POS/Sales needs to offer a product (§33). No price — Pricing owns it."""

    product_id: str
    name: str
    base_unit_id: str
    sellable_now: bool
    catch_weight_enabled: bool
    primary_barcode: str | None
    is_bundle: bool
    has_sales_recipe: bool
    tax_profile_id: str | None


@dataclass(frozen=True)
class QualityProductConfigDTO:
    """What Quality needs to inspect a product (§34)."""

    product_id: str
    inspection_required: bool
    temperature_required: bool
    quarantine_required: bool
    requires_cold_chain: bool
    minimum_remaining_for_receipt: int | None

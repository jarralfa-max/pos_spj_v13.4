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
class PurchaseUnitDTO:
    """Una unidad en la que se puede comprar el producto: ``1 code = factor_to_base``
    unidades base. La unidad base misma va con factor 1."""

    unit_id: str
    code: str
    name: str
    dimension: str
    factor_to_base: str
    is_base: bool
    product_specific: bool
    conversion_id: str | None = None
    #: §27: se puede recibir en fracción. La unidad base siempre puede.
    fractional_receipt: bool = True


@dataclass(frozen=True)
class PurchaseProductConfigDTO:
    """What Purchasing needs to buy a product (§31). No final price here.

    Las unidades de compra, su conversión y la base de precio salen de aquí: Compras
    no las define ni deja capturarlas."""

    product_id: str
    purchasable: bool
    base_unit_id: str
    is_meat: bool
    species_id: str | None
    catch_weight_enabled: bool
    requires_cold_chain: bool
    inspection_required: bool
    supplier_codes: tuple[str, ...]
    code: str = ""
    name: str = ""
    base_unit_code: str = ""
    base_unit_name: str = ""
    base_unit_dimension: str = ""
    purchase_units: tuple[PurchaseUnitDTO, ...] = ()
    price_basis: str | None = None
    lot_controlled: bool = False
    expiration_controlled: bool = False
    # §25: lo que la RECEPCIÓN debe capturar, también desde el maestro.
    temperature_required: bool = False
    serial_controlled: bool = False


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


@dataclass(frozen=True)
class ProcessingProductConfigDTO:
    """What Processing freezes about a product it transforms: its classification,
    as data (species/category), so tolerances can be overridden per species or
    category without any species-specific code."""

    product_id: str
    species_id: str | None
    category_id: str | None

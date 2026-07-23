"""Canonical enums for the products bounded context.

PROD-2 defines the master-data vocabulary: product types (§10), lifecycle states,
and functional roles (§5). Meat classification enums (Species/MeatCategory/…) land
in PROD-3. All values are stable UPPER_SNAKE strings so they survive persistence
and cross the wire unchanged.
"""

from __future__ import annotations

from enum import Enum


class ProductType(str, Enum):
    """What an article *is* (§10). Drives which roles/profiles are required."""

    RESALE_PRODUCT = "RESALE_PRODUCT"
    RAW_MATERIAL = "RAW_MATERIAL"
    LIVE_ANIMAL = "LIVE_ANIMAL"
    CARCASS = "CARCASS"
    HALF_CARCASS = "HALF_CARCASS"
    QUARTER = "QUARTER"
    PRIMARY_CUT = "PRIMARY_CUT"
    SECONDARY_CUT = "SECONDARY_CUT"
    TRIM = "TRIM"
    GROUND_MEAT = "GROUND_MEAT"
    OFFAL = "OFFAL"
    BY_PRODUCT = "BY_PRODUCT"
    CO_PRODUCT = "CO_PRODUCT"
    WASTE = "WASTE"
    SEMI_FINISHED_GOOD = "SEMI_FINISHED_GOOD"
    FINISHED_GOOD = "FINISHED_GOOD"
    PRODUCTION_COMPONENT = "PRODUCTION_COMPONENT"
    PACKAGING_MATERIAL = "PACKAGING_MATERIAL"
    CONSUMABLE = "CONSUMABLE"
    MRO_MATERIAL = "MRO_MATERIAL"
    SPARE_PART = "SPARE_PART"
    SERVICE = "SERVICE"
    VIRTUAL_BUNDLE = "VIRTUAL_BUNDLE"
    STOCKED_KIT = "STOCKED_KIT"
    RETURNABLE_CONTAINER = "RETURNABLE_CONTAINER"


# Tipos cárnicos que exigen especie + clasificación (§7, §11). Se valida en la
# policy de creación; la clasificación concreta llega en PROD-3.
MEAT_PRODUCT_TYPES = frozenset({
    ProductType.LIVE_ANIMAL,
    ProductType.CARCASS,
    ProductType.HALF_CARCASS,
    ProductType.QUARTER,
    ProductType.PRIMARY_CUT,
    ProductType.SECONDARY_CUT,
    ProductType.TRIM,
    ProductType.GROUND_MEAT,
    ProductType.OFFAL,
})

# Tipos que nunca se manejan en inventario/POS como stock vendible por defecto.
SERVICE_TYPES = frozenset({ProductType.SERVICE, ProductType.VIRTUAL_BUNDLE})


class LifecycleStatus(str, Enum):
    """Estado del ciclo de vida del producto (§10)."""

    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    BLOCKED = "BLOCKED"
    DISCONTINUED = "DISCONTINUED"
    ARCHIVED = "ARCHIVED"


class ProductRole(str, Enum):
    """Roles funcionales que un producto puede acumular (§5).

    Un producto interno puede existir en inventario, ser input/output de receta y
    no estar disponible en POS. Los roles no son excluyentes.
    """

    PURCHASABLE = "PURCHASABLE"
    SELLABLE = "SELLABLE"
    INVENTORY_MANAGED = "INVENTORY_MANAGED"
    PRODUCIBLE = "PRODUCIBLE"
    CONSUMABLE = "CONSUMABLE"
    INTERNAL_ONLY = "INTERNAL_ONLY"
    QUALITY_CONTROLLED = "QUALITY_CONTROLLED"
    TRACEABLE = "TRACEABLE"
    COSTED = "COSTED"

"""Integration query services (§30-34) — read contracts for other contexts.

All keyed by ``product_id``. These services ONLY read the products schema; they
never touch inventory balances (Inventory owns stock) and never return a final
price (Pricing owns price). The absence of those reads is a guardrail
(``test_products_do_not_read_inventory_balances``).
"""

from __future__ import annotations

from backend.application.products.queries.integration_dtos import (
    InventoryProductConfigDTO,
    PosProductDTO,
    PurchaseProductConfigDTO,
    QualityProductConfigDTO,
)
from backend.domain.products.enums import MEAT_PRODUCT_TYPES, LifecycleStatus, ProductType
from backend.infrastructure.db.repositories.products.profile_repository import (
    ProfileRepository,
)


def _product_row(conn, product_id: str):
    return conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()


def _is_meat(row) -> bool:
    return ProductType(row["product_type"]) in MEAT_PRODUCT_TYPES


class InventoryProductConfigQueryService:
    """§30 — Inventory reads flags, never the other way around."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def get(self, product_id: str) -> InventoryProductConfigDTO | None:
        row = _product_row(self._conn, product_id)
        if row is None:
            return None
        return InventoryProductConfigDTO(
            product_id=row["id"], base_unit_id=row["base_unit_id"],
            inventory_managed=bool(row["inventory_managed"]),
            lot_controlled=bool(row["lot_controlled"]),
            serial_controlled=bool(row["serial_controlled"]),
            expiration_controlled=bool(row["expiration_controlled"]),
            catch_weight_enabled=bool(row["catch_weight_enabled"]),
            quality_controlled=bool(row["quality_controlled"]),
            traceability_required=bool(row["traceability_required"]))


class PurchaseProductConfigQueryService:
    """§31 — Purchasing reads buy config + supplier codes."""

    def __init__(self, connection) -> None:
        self._conn = connection
        self._profiles = ProfileRepository(connection)

    def get(self, product_id: str) -> PurchaseProductConfigDTO | None:
        row = _product_row(self._conn, product_id)
        if row is None:
            return None
        codes = tuple(r["code"] for r in self._conn.execute(
            "SELECT code FROM product_alternate_codes "
            "WHERE product_id=? AND active=1 AND code_type='SUPPLIER_CODE'",
            (product_id,)).fetchall())
        logistics = self._profiles.get_logistics(product_id)
        quality = self._profiles.get_quality(product_id)
        return PurchaseProductConfigDTO(
            product_id=row["id"], purchasable=bool(row["purchasable"]),
            base_unit_id=row["base_unit_id"], is_meat=_is_meat(row),
            species_id=row["species_id"],
            catch_weight_enabled=bool(row["catch_weight_enabled"]),
            requires_cold_chain=bool(logistics.requires_cold_chain) if logistics else False,
            inspection_required=bool(quality.inspection_required) if quality else False,
            supplier_codes=codes)


class PosCatalogQueryService:
    """§33 — POS only sees ACTIVE, sellable, branch-enabled products. No price."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def get(self, product_id: str) -> PosProductDTO | None:
        row = _product_row(self._conn, product_id)
        if row is None:
            return None
        barcode = self._conn.execute(
            "SELECT barcode_value FROM product_barcodes "
            "WHERE product_id=? AND active=1 ORDER BY is_primary DESC LIMIT 1",
            (product_id,)).fetchone()
        is_bundle = self._conn.execute(
            "SELECT 1 FROM product_bundles WHERE product_id=? AND active=1 LIMIT 1",
            (product_id,)).fetchone() is not None
        has_recipe = self._conn.execute(
            "SELECT 1 FROM recipes WHERE product_id=? AND recipe_type='SALES_EXPLOSION' "
            "AND active=1 LIMIT 1", (product_id,)).fetchone() is not None
        sellable_now = (LifecycleStatus(row["lifecycle_status"]) is LifecycleStatus.ACTIVE
                        and bool(row["sellable"]) and not bool(row["internal_only"]))
        return PosProductDTO(
            product_id=row["id"], name=row["name"], base_unit_id=row["base_unit_id"],
            sellable_now=sellable_now, catch_weight_enabled=bool(row["catch_weight_enabled"]),
            primary_barcode=barcode["barcode_value"] if barcode else None,
            is_bundle=is_bundle, has_sales_recipe=has_recipe,
            tax_profile_id=row["tax_profile_id"])

    def is_offered_at_branch(self, product_id: str, branch_id: str) -> bool:
        dto = self.get(product_id)
        if dto is None or not dto.sellable_now:
            return False
        row = self._conn.execute(
            "SELECT enabled FROM branch_product WHERE product_id=? AND branch_id=?",
            (product_id, branch_id)).fetchone()
        return bool(row["enabled"]) if row else False


class QualityProductConfigQueryService:
    """§34 — Quality reads inspection/shelf-life/cold-chain requirements."""

    def __init__(self, connection) -> None:
        self._conn = connection
        self._profiles = ProfileRepository(connection)

    def get(self, product_id: str) -> QualityProductConfigDTO | None:
        row = _product_row(self._conn, product_id)
        if row is None:
            return None
        quality = self._profiles.get_quality(product_id)
        logistics = self._profiles.get_logistics(product_id)
        shelf = self._profiles.get_shelf_life(product_id)
        return QualityProductConfigDTO(
            product_id=row["id"],
            inspection_required=bool(quality.inspection_required) if quality else False,
            temperature_required=bool(quality.temperature_required) if quality else False,
            quarantine_required=bool(quality.quarantine_required) if quality else False,
            requires_cold_chain=bool(logistics.requires_cold_chain) if logistics else False,
            minimum_remaining_for_receipt=(
                shelf.minimum_remaining_for_receipt if shelf else None))

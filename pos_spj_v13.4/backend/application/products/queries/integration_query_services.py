"""Integration query services (§30-34) — read contracts for other contexts.

All keyed by ``product_id``. These services ONLY read the products schema; they
never touch inventory balances (Inventory owns stock) and never return a final
price (Pricing owns price). The absence of those reads is a guardrail
(``test_products_do_not_read_inventory_balances``).
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation

from backend.application.products.queries.integration_dtos import (
    InventoryProductConfigDTO,
    PosProductDTO,
    ProcessingProductConfigDTO,
    PurchaseProductConfigDTO,
    PurchaseUnitDTO,
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
    """§31 — Purchasing reads buy config, purchase units + supplier codes.

    Compras NO define unidades: la base, las presentaciones (``product_unit_
    conversions`` hacia/desde la base) y la base de precio de peso variable se
    leen aquí. Tolera esquemas reducidos y conexiones sin ``sqlite3.Row`` (hay
    tablas ``products`` fabricadas a mano en muchas pruebas): una columna o
    tabla ausente se trata como dato no configurado, nunca como fallo.
    """

    def __init__(self, connection) -> None:
        self._conn = connection
        self._profiles = ProfileRepository(connection)

    def _one(self, sql: str, params=()):
        cursor = self._conn.cursor()
        cursor.row_factory = sqlite3.Row
        try:
            return cursor.execute(sql, params).fetchone()
        except sqlite3.OperationalError:
            return None

    def _all(self, sql: str, params=()) -> list:
        cursor = self._conn.cursor()
        cursor.row_factory = sqlite3.Row
        try:
            return cursor.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []

    def get(self, product_id: str) -> PurchaseProductConfigDTO | None:
        row = self._one("SELECT * FROM products WHERE id=?", (product_id,))
        if row is None:
            return None
        keys = set(row.keys())

        def col(name, default=None):
            return row[name] if name in keys else default

        codes = tuple(r["code"] for r in self._all(
            "SELECT code FROM product_alternate_codes "
            "WHERE product_id=? AND active=1 AND code_type='SUPPLIER_CODE'",
            (product_id,)))
        try:
            logistics = self._profiles.get_logistics(product_id)
            quality = self._profiles.get_quality(product_id)
        except (sqlite3.OperationalError, TypeError, IndexError):
            logistics = quality = None
        base_ref = str(col("base_unit_id") or "")
        base = self._unit(base_ref)
        catch_weight = bool(col("catch_weight_enabled", 0))
        product_type = col("product_type")
        try:
            is_meat = ProductType(product_type) in MEAT_PRODUCT_TYPES
        except ValueError:
            is_meat = False
        return PurchaseProductConfigDTO(
            product_id=row["id"], purchasable=bool(col("purchasable", 1)),
            base_unit_id=base_ref, is_meat=is_meat,
            species_id=col("species_id"),
            catch_weight_enabled=catch_weight,
            requires_cold_chain=bool(logistics.requires_cold_chain) if logistics else False,
            inspection_required=bool(quality.inspection_required) if quality else False,
            supplier_codes=codes,
            code=str(col("code") or ""), name=str(col("name") or ""),
            base_unit_code=base[1], base_unit_name=base[2], base_unit_dimension=base[3],
            purchase_units=self._purchase_units(product_id, base) if base_ref else (),
            price_basis=self._price_basis(product_id) if catch_weight else None,
            lot_controlled=bool(col("lot_controlled", 0)),
            expiration_controlled=bool(col("expiration_controlled", 0)),
            temperature_required=bool(
                (quality and getattr(quality, "temperature_required", False))
                or (logistics and getattr(logistics, "requires_cold_chain", False))),
            serial_controlled=bool(col("serial_controlled", 0)))

    def _unit(self, ref: str) -> tuple[str, str, str, str]:
        """``(id, código, nombre, dimensión)``. Acepta id o código (hay datos
        viejos con el código en ``base_unit_id``); sin catálogo, el propio valor."""
        if not ref:
            return "", "", "", ""
        row = self._one("SELECT id, code, name, dimension FROM units_of_measure"
                        " WHERE id=? OR code=? ORDER BY (id=?) DESC LIMIT 1", (ref, ref, ref))
        if row is None:
            return ref, ref, ref, ""
        return (str(row["id"]), str(row["code"]), str(row["name"] or row["code"]),
                str(row["dimension"] or ""))

    def _purchase_units(self, product_id: str, base) -> tuple[PurchaseUnitDTO, ...]:
        base_id, base_code, base_name, base_dimension = base
        units: dict[str, PurchaseUnitDTO] = {base_code: PurchaseUnitDTO(
            unit_id=base_id, code=base_code, name=base_name, dimension=base_dimension,
            factor_to_base="1", is_base=True, product_specific=False)}
        rows = self._all(
            "SELECT * FROM product_unit_conversions"
            " WHERE active=1 AND (product_id=? OR product_id IS NULL)"
            " AND (from_unit_id=? OR to_unit_id=?)"
            " AND (effective_from IS NULL OR effective_from <= datetime('now'))"
            " AND (effective_to IS NULL OR effective_to >= datetime('now'))"
            " ORDER BY (product_id IS NULL)", (product_id, base_id, base_id))
        for r in rows:
            try:
                factor = Decimal(str(r["factor"]))
            except (InvalidOperation, ValueError):
                continue
            if factor <= 0:
                continue
            if r["to_unit_id"] == base_id:
                other_ref, to_base = r["from_unit_id"], factor
            else:
                other_ref, to_base = r["to_unit_id"], Decimal("1") / factor
            other = self._unit(str(other_ref))
            if other[1] in units:
                continue   # la específica del producto gana (van primero)
            units[other[1]] = PurchaseUnitDTO(
                unit_id=other[0], code=other[1], name=other[2], dimension=other[3],
                factor_to_base=format(to_base.normalize(), "f"), is_base=False,
                product_specific=r["product_id"] is not None, conversion_id=str(r["id"]),
                fractional_receipt=_fractional(r))
        return tuple(units.values())

    def _price_basis(self, product_id: str) -> str | None:
        row = self._one("SELECT enabled, price_basis FROM product_catch_weight_config"
                        " WHERE product_id=?", (product_id,))
        if row is None or not row["enabled"]:
            return None
        return str(row["price_basis"] or "") or None


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


class ProcessingProductConfigQueryService:
    """Processing reads a product's classification (species/category) — data,
    never behavior."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def get(self, product_id: str) -> ProcessingProductConfigDTO | None:
        row = _product_row(self._conn, product_id)
        if row is None:
            return None
        return ProcessingProductConfigDTO(
            product_id=row["id"], species_id=row["species_id"], category_id=row["category_id"])


def _fractional(row) -> bool:
    """`allow_fractional_receipt` (migración 286); sin la columna, se permite."""
    try:
        keys = row.keys()
    except AttributeError:
        return True
    return bool(row["allow_fractional_receipt"]) if "allow_fractional_receipt" in keys else True

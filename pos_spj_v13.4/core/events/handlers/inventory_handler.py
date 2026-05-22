# core/events/handlers/inventory_handler.py — SPJ ERP FASE 5
"""
SaleInventoryHandler — deducts stock when SALE_ITEMS_PROCESS is received.

FASE 5 upgrade: composite (compuesto) items are now resolved through
RecipeResolver, which performs recursive BOM explosion with cycle detection.
Deductions for the same leaf product from different BOM paths are merged
before writing to inventory (one movement record per leaf product per sale line).

Registered by wiring.py at priority=100 (sync, inside SAVEPOINT).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger("spj.handlers.inventory")


class SaleInventoryHandler:
    """
    Subscribes to SALE_ITEMS_PROCESS and deducts stock via InventoryService.

    Args:
        inventory_service: Must implement deduct_stock(...).
        db:                Raw DB connection used by RecipeResolver for BOM
                           lookup. Must be the same connection inside the
                           active SAVEPOINT so recipe reads are consistent.
        recipe_repo:       Deprecated — ignored. Kept for call-site compatibility.
    """

    def __init__(self, inventory_service, db=None, recipe_repo=None):
        self._inv = inventory_service
        self._db  = db
        if recipe_repo is not None and db is None:
            logger.warning(
                "SaleInventoryHandler: recipe_repo is deprecated — "
                "pass db= for RecipeResolver-based BOM expansion"
            )

    # ── Public handler ────────────────────────────────────────────────────────

    def handle(self, payload: Dict[str, Any]) -> None:
        branch_id    = int(payload.get("branch_id", payload.get("sucursal_id", 1)))
        operation_id = str(payload.get("operation_id") or payload.get("sale_id", "EVT"))
        sale_id      = str(payload.get("sale_id", payload.get("venta_id", "")))
        user         = str(payload.get("user", payload.get("usuario", "sistema")))
        folio        = str(payload.get("folio", ""))

        for item in payload.get("items", []):
            product_id = item.get("product_id")
            qty        = float(item.get("qty", item.get("cantidad", 0)))

            if qty <= 0 or not product_id:
                continue

            try:
                if item.get("es_compuesto", 0) == 1:
                    self._deduct_via_bom(item, branch_id, sale_id, operation_id, user, folio)
                else:
                    self._inv.deduct_stock(
                        product_id=product_id,
                        branch_id=branch_id,
                        qty=qty,
                        operation_id=operation_id,
                        reference_type="VENTA",
                        reference_id=sale_id,
                        user=user,
                        notes=f"Salida por venta {folio}",
                    )
            except Exception as exc:
                logger.error(
                    "SaleInventoryHandler: error deducting product=%s qty=%.4f folio=%s: %s",
                    product_id, qty, folio, exc,
                )
                raise  # re-raise so the SAVEPOINT can roll back

    # ── BOM-aware composite deduction ─────────────────────────────────────────

    def _deduct_via_bom(
        self,
        item: Dict[str, Any],
        branch_id: int,
        sale_id: str,
        operation_id: str,
        user: str,
        folio: str,
    ) -> None:
        """
        Resolve the BOM for a composite item and deduct each leaf component.

        Uses RecipeResolver when a db connection is available.
        Falls back to the legacy single-level lookup when db is not set.
        Merges quantities for the same product_id across BOM paths before
        writing to inventory to avoid duplicate movement records.
        """
        product_id = item["product_id"]
        sale_qty   = float(item.get("qty", item.get("cantidad", 0)))

        if self._db is not None:
            self._deduct_via_resolver(
                product_id=product_id,
                sale_qty=sale_qty,
                branch_id=branch_id,
                sale_id=sale_id,
                operation_id=operation_id,
                user=user,
                folio=folio,
            )
        else:
            # Legacy fallback (no db — single-level only)
            logger.warning(
                "SaleInventoryHandler: no db — falling back to legacy "
                "single-level BOM for composite product %s", product_id
            )
            self._deduct_legacy_single_level(
                item=item,
                branch_id=branch_id,
                sale_id=sale_id,
                operation_id=operation_id,
                user=user,
                folio=folio,
            )

    def _deduct_via_resolver(
        self,
        product_id: int,
        sale_qty: float,
        branch_id: int,
        sale_id: str,
        operation_id: str,
        user: str,
        folio: str,
    ) -> None:
        from core.services.recipes.recipe_resolver import RecipeResolver

        resolver  = RecipeResolver(self._db)
        explosion = resolver.resolve_for_sale(product_id, sale_qty, branch_id)

        if explosion.cycle_detected:
            # P0-3: block the sale — a cyclic BOM cannot produce valid deductions.
            # Logging alone would let the sale commit with empty or wrong movements.
            raise ValueError(
                f"El producto ID={product_id} tiene una receta con referencia circular. "
                "Corrige la receta en el módulo Recetas antes de vender este producto."
            )

        # Resolver falls back to a virtual self-deduction when no recipe exists.
        # That's not valid for sales — raise so the UI can prompt to create a recipe.
        no_recipe = (
            not explosion.deductions
            or (
                len(explosion.deductions) == 1
                and explosion.deductions[0].product_id == product_id
                and explosion.deductions[0].is_virtual
            )
        )
        if no_recipe:
            raise ValueError(
                f"El producto compuesto ID={product_id} no tiene receta activa. "
                "Crea la receta en el módulo Recetas antes de vender este producto."
            )

        # Merge quantities for the same leaf product (diamond dependency)
        merged: Dict[int, float] = {}
        for line in explosion.deductions:
            merged[line.product_id] = merged.get(line.product_id, 0.0) + line.quantity

        for leaf_product_id, leaf_qty in merged.items():
            if leaf_qty <= 0:
                continue
            self._inv.deduct_stock(
                product_id=leaf_product_id,
                branch_id=branch_id,
                qty=round(leaf_qty, 4),
                operation_id=operation_id,
                reference_type="VENTA_BOM",
                reference_id=sale_id,
                user=user,
                notes=f"BOM venta {folio} ← producto {product_id}",
            )

    def _deduct_legacy_single_level(
        self,
        item: Dict[str, Any],
        branch_id: int,
        sale_id: str,
        operation_id: str,
        user: str,
        folio: str,
    ) -> None:
        """Single-level BOM lookup via InventoryService for backward compatibility."""
        inv = self._inv
        if not hasattr(inv, "_recipes") or inv._recipes is None:
            logger.warning(
                "SaleInventoryHandler legacy: no recipe source for product %s — skipped",
                item.get("product_id")
            )
            return

        recipe_items = inv._recipes.get_recipe_items_by_product(item["product_id"])
        if not recipe_items:
            raise ValueError(
                f"El combo ID {item['product_id']} no tiene receta. "
                "Crea la receta en el módulo Recetas."
            )

        sale_qty = float(item.get("qty", item.get("cantidad", 0)))
        for sub_item in recipe_items:
            rend_pct = float(sub_item.get("rendimiento_pct") or 0)
            cantidad  = float(sub_item.get("cantidad") or 0)

            if rend_pct > 0:
                qty_to_deduct = sale_qty * rend_pct / 100.0
            elif cantidad > 0:
                qty_to_deduct = sale_qty * cantidad
            else:
                continue

            if qty_to_deduct <= 0:
                continue

            self._inv.deduct_stock(
                product_id=sub_item["component_product_id"],
                branch_id=branch_id,
                qty=round(qty_to_deduct, 4),
                operation_id=operation_id,
                reference_type="VENTA_COMBO",
                reference_id=sale_id,
                user=user,
                notes=f"Consumo receta {folio}",
            )

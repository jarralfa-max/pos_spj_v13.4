# core/events/handlers/inventory_handler.py — SPJ ERP FASE 5
"""
SaleInventoryHandler — deducts stock when SALE_ITEMS_PROCESS is received.

Composite (compuesto) items are resolved through RecipeResolver. Simple sale
lines and BOM components are consolidated by product before mutating inventory
so each sale creates one movement per product/branch/reference type.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("spj.handlers.inventory")


class SaleInventoryHandler:
    """Subscribes to SALE_ITEMS_PROCESS and deducts stock canonically."""

    def __init__(self, inventory_service, db=None, recipe_repo=None):
        self._inv = inventory_service
        self._db = db
        if recipe_repo is not None and db is None:
            logger.warning(
                "SaleInventoryHandler: recipe_repo is deprecated — "
                "pass db= for RecipeResolver-based BOM expansion"
            )

    def handle(self, payload: Dict[str, Any]) -> None:
        branch_id = int(payload.get("branch_id", payload.get("sucursal_id", 1)))
        operation_id = str(payload.get("operation_id") or payload.get("sale_id", "EVT"))
        sale_id = str(payload.get("sale_id", payload.get("venta_id", "")))
        user = str(payload.get("user", payload.get("usuario", "sistema")))
        folio = str(payload.get("folio", ""))

        simple_totals: dict[int, float] = {}
        simple_units: dict[int, str] = {}
        bom_totals: dict[int, float] = {}

        for item in payload.get("items", []):
            product_id = int(item.get("product_id") or 0)
            qty = float(item.get("qty", item.get("cantidad", 0)) or 0.0)
            if qty <= 0 or not product_id:
                continue
            try:
                if int(item.get("es_compuesto", 0) or 0) == 1:
                    for component_id, component_qty in self._resolve_bom_totals(
                        item=item,
                        branch_id=branch_id,
                        sale_id=sale_id,
                        operation_id=operation_id,
                        user=user,
                        folio=folio,
                    ).items():
                        bom_totals[component_id] = bom_totals.get(component_id, 0.0) + component_qty
                else:
                    simple_totals[product_id] = simple_totals.get(product_id, 0.0) + qty
                    simple_units.setdefault(product_id, str(item.get("unit") or item.get("unidad") or "unit"))
            except Exception as exc:
                logger.error(
                    "SaleInventoryHandler: error resolving product=%s qty=%.4f folio=%s: %s",
                    product_id,
                    qty,
                    folio,
                    exc,
                )
                raise

        for product_id, qty in simple_totals.items():
            self._decrease_or_raise(
                product_id=product_id,
                branch_id=branch_id,
                quantity=round(qty, 4),
                unit=simple_units.get(product_id, "unit"),
                operation_id=operation_id,
                source_module="sales",
                reference_type="SALE",
                reference_id=sale_id,
                user_name=user,
                reason=f"Salida por venta {folio}",
            )

        for component_id, qty in bom_totals.items():
            self._decrease_or_raise(
                product_id=component_id,
                branch_id=branch_id,
                quantity=round(qty, 4),
                unit="unit",
                operation_id=operation_id,
                source_module="sales",
                reference_type="SALE_BOM",
                reference_id=sale_id,
                user_name=user,
                reason=f"BOM venta {folio}",
            )

    def _decrease_or_raise(self, **kwargs: Any) -> None:
        result = self._inv.decrease_stock(auto_commit=False, **kwargs)
        if not getattr(result, "success", False):
            message = getattr(result, "message", "") or "No se pudo descontar inventario de la venta."
            raise RuntimeError(message)

    def _resolve_bom_totals(
        self,
        item: Dict[str, Any],
        branch_id: int,
        sale_id: str,
        operation_id: str,
        user: str,
        folio: str,
    ) -> dict[int, float]:
        product_id = int(item["product_id"])
        sale_qty = float(item.get("qty", item.get("cantidad", 0)) or 0.0)

        if self._db is not None:
            return self._resolve_bom_with_resolver(product_id, sale_qty, branch_id)

        logger.warning(
            "SaleInventoryHandler: no db — falling back to legacy single-level BOM for composite product %s",
            product_id,
        )
        return self._resolve_legacy_single_level(item, sale_qty, sale_id, operation_id, user, folio)

    def _resolve_bom_with_resolver(self, product_id: int, sale_qty: float, branch_id: int) -> dict[int, float]:
        from core.services.recipes.recipe_resolver import RecipeResolver

        resolver = RecipeResolver(self._db)
        explosion = resolver.resolve_for_sale(product_id, sale_qty, branch_id)
        if explosion.cycle_detected:
            raise ValueError(
                f"El producto ID={product_id} tiene una receta con referencia circular. "
                "Corrige la receta en el módulo Recetas antes de vender este producto."
            )
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
        merged: dict[int, float] = {}
        for line in explosion.deductions:
            merged[int(line.product_id)] = merged.get(int(line.product_id), 0.0) + float(line.quantity or 0.0)
        return {pid: qty for pid, qty in merged.items() if qty > 0}

    def _resolve_legacy_single_level(
        self,
        item: Dict[str, Any],
        sale_qty: float,
        sale_id: str,
        operation_id: str,
        user: str,
        folio: str,
    ) -> dict[int, float]:
        inv = self._inv
        if not hasattr(inv, "_recipes") or inv._recipes is None:
            logger.warning(
                "SaleInventoryHandler legacy: no recipe source for product %s — skipped",
                item.get("product_id"),
            )
            return {}
        recipe_items = inv._recipes.get_recipe_items_by_product(item["product_id"])
        if not recipe_items:
            raise ValueError(f"El combo ID {item['product_id']} no tiene receta. Crea la receta en el módulo Recetas.")
        merged: dict[int, float] = {}
        for sub_item in recipe_items:
            rend_pct = float(sub_item.get("rendimiento_pct") or 0)
            cantidad = float(sub_item.get("cantidad") or 0)
            if rend_pct > 0:
                qty_to_deduct = sale_qty * rend_pct / 100.0
            elif cantidad > 0:
                qty_to_deduct = sale_qty * cantidad
            else:
                continue
            if qty_to_deduct <= 0:
                continue
            component_id = int(sub_item["component_product_id"])
            merged[component_id] = merged.get(component_id, 0.0) + qty_to_deduct
        return merged

    # Backward-compatible method names used by older tests/callers.
    def _deduct_via_bom(self, item, branch_id, sale_id, operation_id, user, folio) -> None:
        totals = self._resolve_bom_totals(item, branch_id, sale_id, operation_id, user, folio)
        for product_id, quantity in totals.items():
            self._decrease_or_raise(
                product_id=product_id,
                branch_id=branch_id,
                quantity=round(quantity, 4),
                unit="unit",
                operation_id=operation_id,
                source_module="sales",
                reference_type="SALE_BOM",
                reference_id=sale_id,
                user_name=user,
                reason=f"BOM venta {folio}",
            )

    def _deduct_via_resolver(self, product_id, sale_qty, branch_id, sale_id, operation_id, user, folio) -> None:
        totals = self._resolve_bom_with_resolver(int(product_id), float(sale_qty), int(branch_id))
        for component_id, quantity in totals.items():
            self._decrease_or_raise(
                product_id=component_id,
                branch_id=branch_id,
                quantity=round(quantity, 4),
                unit="unit",
                operation_id=operation_id,
                source_module="sales",
                reference_type="SALE_BOM",
                reference_id=sale_id,
                user_name=user,
                reason=f"BOM venta {folio} ← producto {product_id}",
            )

    def _deduct_legacy_single_level(self, item, branch_id, sale_id, operation_id, user, folio) -> None:
        totals = self._resolve_legacy_single_level(item, float(item.get("qty", item.get("cantidad", 0)) or 0.0), sale_id, operation_id, user, folio)
        for component_id, quantity in totals.items():
            self._decrease_or_raise(
                product_id=component_id,
                branch_id=branch_id,
                quantity=round(quantity, 4),
                unit="unit",
                operation_id=operation_id,
                source_module="sales",
                reference_type="SALE_BOM",
                reference_id=sale_id,
                user_name=user,
                reason=f"Consumo receta {folio}",
            )

# core/events/handlers/inventory_handler.py — SPJ ERP v13.4  Phase 1
"""
SaleInventoryHandler — deducts stock when SALE_ITEMS_PROCESS is received.

Extracted from sales_service.py (Phase 1 decoupling).
Registered by wiring.py at priority=100 (sync, inside SAVEPOINT).

Handles both simple items and composite recipes.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("spj.handlers.inventory")


class SaleInventoryHandler:
    """
    Subscribes to SALE_ITEMS_PROCESS and deducts stock via InventoryService.

    Args:
        inventory_service: Must implement deduct_stock(...).
        recipe_repo:       Optional. Required only for composite (combo) items.
    """

    def __init__(self, inventory_service, recipe_repo=None):
        self._inv = inventory_service
        self._recipes = recipe_repo

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
                    self._deduct_combo(item, branch_id, sale_id, operation_id, user, folio)
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
                raise  # re-raise so the SAVEPOINT can roll back if needed

    def _deduct_combo(
        self,
        item: Dict[str, Any],
        branch_id: int,
        sale_id: str,
        operation_id: str,
        user: str,
        folio: str,
    ) -> None:
        if not self._recipes:
            logger.warning("SaleInventoryHandler: no recipe_repo — skipping combo %s", item.get("product_id"))
            return

        recipe_items = self._recipes.get_recipe_items_by_product(item["product_id"])
        if not recipe_items:
            raise ValueError(
                f"El combo ID {item['product_id']} no tiene receta. "
                f"Crea la receta en el módulo Recetas."
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
                logger.warning(
                    "SaleInventoryHandler: recipe component pid=%s has no qty/rendimiento — skipped",
                    sub_item.get("component_product_id"),
                )
                continue

            if qty_to_deduct <= 0:
                continue

            tipo_receta = sub_item.get("tipo_receta", "combinacion")
            self._inv.deduct_stock(
                product_id=sub_item["component_product_id"],
                branch_id=branch_id,
                qty=round(qty_to_deduct, 4),
                operation_id=operation_id,
                reference_type="VENTA_COMBO",
                reference_id=sale_id,
                user=user,
                notes=f"Consumo receta {folio} ({tipo_receta})",
            )

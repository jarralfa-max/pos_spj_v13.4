# core/events/handlers/purchase_handler.py — Phase 4
"""
PurchaseInventoryHandler — handles PURCHASE_ITEMS_PROCESS.
PurchaseFinanceHandler   — handles PURCHASE_CREATED (post-transaction).

Registered by wiring.py.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("spj.handlers.purchase")


class PurchaseInventoryHandler:
    """
    Subscribes to PURCHASE_ITEMS_PROCESS and applies inventory IN for each
    purchased item via inventory_service.add_stock().

    Payload expected:
        items        — list of {product_id, qty, unit_cost, nombre?}
        branch_id    — branch receiving the goods
        operation_id — idempotency key
        compra_id    — purchase record ID
        folio        — purchase folio for notes
        user         — usuario triggering the purchase
    """

    def __init__(self, inventory_service):
        self._inv = inventory_service

    def handle(self, payload: Dict[str, Any]) -> None:
        branch_id = str(payload.get("branch_id") or "")
        operation_id = str(payload.get("operation_id", ""))
        compra_id    = payload.get("compra_id", "")
        folio        = str(payload.get("folio", ""))
        user         = str(payload.get("user", payload.get("usuario", "sistema")))

        for item in payload.get("items", []):
            product_id = item.get("product_id")
            qty        = float(item.get("qty", item.get("cantidad", 0)))
            unit_cost  = float(item.get("unit_cost", item.get("costo_unit", 0)))

            if qty <= 0 or not product_id:
                continue

            try:
                self._inv.add_stock(
                    product_id     = product_id,
                    branch_id      = branch_id,
                    qty            = qty,
                    unit_cost      = unit_cost,
                    reference_type = "COMPRA",
                    reference_id   = str(compra_id),
                    operation_id   = f"{operation_id}_{product_id}",
                    user           = user,
                    notes          = f"Entrada por compra {folio}",
                )
            except Exception as exc:
                logger.error(
                    "PurchaseInventoryHandler: error product=%s qty=%.4f folio=%s: %s",
                    product_id, qty, folio, exc,
                )
                raise


class PurchaseFinanceHandler:
    """
    Subscribes to PURCHASE_CREATED (post-transaction) and records the
    double-entry journal for cost of goods: inventario_almacen / cuentas_por_pagar.

    Respects supplier logic and cost calculations already computed by ProcesarCompraUC.
    Only fires if finance_service is available and total > 0.
    """

    def __init__(self, finance_service):
        self._finance = finance_service

    def handle(self, payload: Dict[str, Any]) -> None:
        total       = float(payload.get("total", 0))
        if total <= 0:
            return

        folio       = str(payload.get("folio", ""))
        compra_id   = payload.get("compra_id", payload.get("purchase_id"))
        sucursal_id = str(payload.get("sucursal_id") or payload.get("branch_id") or "")
        usuario     = str(payload.get("usuario", payload.get("user", "sistema")))

        try:
            if not hasattr(self._finance, "registrar_asiento"):
                return
            self._finance.registrar_asiento(
                debe         = "inventario_almacen",
                haber        = "cuentas_por_pagar",
                concepto     = f"Compra {folio} — entrada mercancía",
                monto        = total,
                modulo       = "compras",
                referencia_id= compra_id,
                sucursal_id  = sucursal_id,
                evento       = "PURCHASE_CREATED",
                metadata     = {
                    "folio":       folio,
                    "proveedor_id": payload.get("proveedor_id", payload.get("provider_id")),
                },
            )
        except Exception as exc:
            logger.warning("PurchaseFinanceHandler: %s", exc)

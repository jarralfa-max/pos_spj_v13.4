# core/events/handlers/purchase_handler.py — Phase 4
"""
PurchaseFinanceHandler   — handles PURCHASE_CREATED (post-transaction).

Registered by wiring.py.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("spj.handlers.purchase")



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

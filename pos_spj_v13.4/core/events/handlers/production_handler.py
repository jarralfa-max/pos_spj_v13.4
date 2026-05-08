# core/events/handlers/production_handler.py — Phase 3 + Financial Audit 2026-05-08
"""
ProductionInventoryHandler  — handles PRODUCTION_ITEMS_PROCESS (sync, inside SAVEPOINT).
ProductionFinanceHandler     — handles PRODUCCION_COMPLETADA (post-commit, async).

OUT raw materials and IN derived products when production executes.
Registered by wiring.py:
  PRODUCTION_ITEMS_PROCESS → ProductionInventoryHandler  (priority=100, sync)
  PRODUCCION_COMPLETADA    → ProductionFinanceHandler     (priority=45, async)
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("spj.handlers.production")


class ProductionInventoryHandler:
    """
    Subscribes to PRODUCTION_ITEMS_PROCESS and applies each inventory movement
    via InventoryEngine. Runs synchronously, inside the production transaction.

    The payload must include:
        conn          — the active transaction connection (for atomicity)
        branch_id     — branch performing the production
        operation_id  — base operation ID (movements may override per-item)
        reference_id  — production ID (produccion_id or batch_id)
        reference_type— "PRODUCCION" or "PRODUCTION_BATCH"
        user          — usuario that triggered the production
        movements     — list of dicts: {product_id, delta, movement_type, operation_id?}
    """

    def __init__(self, inventory_engine):
        self._inv = inventory_engine

    def handle(self, payload: Dict[str, Any]) -> None:
        conn       = payload.get("conn")
        branch_id  = int(payload.get("branch_id", 1))
        ref_type   = str(payload.get("reference_type", "PRODUCCION"))
        ref_id     = payload.get("reference_id")
        base_op_id = str(payload.get("operation_id", ""))

        for mov in payload.get("movements", []):
            delta = float(mov.get("delta", 0))
            if abs(delta) < 1e-9:
                continue

            op_id = str(
                mov.get("operation_id")
                or f"{base_op_id}_{mov['product_id']}_{mov.get('movement_type', '')}"
            )

            try:
                self._inv.process_movement(
                    product_id=int(mov["product_id"]),
                    branch_id=branch_id,
                    quantity=delta,
                    movement_type=str(mov.get("movement_type", "PRODUCCION")),
                    operation_id=op_id,
                    reference_id=ref_id,
                    reference_type=ref_type,
                    conn=conn,
                )
            except Exception as exc:
                logger.error(
                    "ProductionInventoryHandler: error product=%s qty=%.4f type=%s: %s",
                    mov.get("product_id"), delta, mov.get("movement_type"), exc,
                )
                raise


class ProductionFinanceHandler:
    """
    Subscribes to PRODUCCION_COMPLETADA (post-commit, async, priority=45).

    Posts the double-entry cost-of-production journal entries:
      1. Raw material consumption:
           Debe:  7001-costo-materia-prima-consumida
           Haber: 1201-inventario-materia-prima
      2. If cost_allocations provided: finished goods creation:
           Debe:  1202-inventario-productos-terminados
           Haber: 7002-costo-produccion-valor-agregado

    Errors are logged but do NOT re-raise (post-commit — production already recorded).
    If finance_service is unavailable or cost data is absent the handler is a no-op.
    """

    def __init__(self, finance_service):
        self._finance = finance_service

    def handle(self, payload: Dict[str, Any]) -> None:
        if not self._finance or not hasattr(self._finance, "registrar_asiento"):
            return

        batch_id    = payload.get("batch_id", "")
        folio       = str(payload.get("folio", batch_id))
        sucursal_id = int(payload.get("sucursal_id", 1))
        cost_allocs = payload.get("cost_allocations") or {}

        # cost_allocations format: {"raw_material_cost": float, "finished_goods_cost": float}
        raw_cost      = float(cost_allocs.get("raw_material_cost", 0))
        finished_cost = float(cost_allocs.get("finished_goods_cost", 0))

        # Fall back to estimating from movements if cost_allocations missing
        if raw_cost <= 0 and finished_cost <= 0:
            movimientos = payload.get("movimientos", 0)
            if movimientos <= 0:
                return  # No cost data available — skip silently

        try:
            if raw_cost > 0:
                self._finance.registrar_asiento(
                    debe         = "7001-costo-materia-prima-consumida",
                    haber        = "1201-inventario-materia-prima",
                    concepto     = f"Consumo MP en producción lote {folio}",
                    monto        = raw_cost,
                    modulo       = "produccion",
                    referencia_id= batch_id,
                    sucursal_id  = sucursal_id,
                    evento       = "PRODUCCION_COMPLETADA",
                    metadata     = {
                        "batch_id":        batch_id,
                        "folio":           folio,
                        "rendimiento_pct": payload.get("rendimiento_pct"),
                    },
                )

            if finished_cost > 0:
                self._finance.registrar_asiento(
                    debe         = "1202-inventario-productos-terminados",
                    haber        = "7002-costo-produccion-valor-agregado",
                    concepto     = f"Generación productos terminados lote {folio}",
                    monto        = finished_cost,
                    modulo       = "produccion",
                    referencia_id= batch_id,
                    sucursal_id  = sucursal_id,
                    evento       = "PRODUCCION_COMPLETADA",
                    metadata     = {"batch_id": batch_id, "folio": folio},
                )

            logger.info(
                "ProductionFinanceHandler: GL posted batch=%s raw=%.2f finished=%.2f",
                batch_id, raw_cost, finished_cost,
            )
        except Exception as exc:
            logger.warning("ProductionFinanceHandler.handle: %s", exc)

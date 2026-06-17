# core/events/handlers/production_handler.py — Phase 3 + FASE 6
"""
ProductionInventoryHandler  — handles PRODUCTION_ITEMS_PROCESS (sync, inside SAVEPOINT).
ProductionFinanceHandler     — handles PRODUCCION_COMPLETADA (post-commit, async).

OUT raw materials and IN derived products when production executes.
Registered by wiring.py:
  PRODUCTION_ITEMS_PROCESS → ProductionInventoryHandler  (priority=100, sync)
  PRODUCCION_COMPLETADA    → ProductionFinanceHandler     (priority=45, async)

FASE 6: ProductionFinanceHandler now accepts db= and uses ProductionCostService to
  1. read actual cost data from production_cost_ledger (not the sparse event payload)
  2. update costo_promedio in productos + inventario_actual for each output product
  3. post accurate double-entry GL journal entries
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
                    product_id=mov["product_id"],
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

    FASE 6: when db= is provided, queries production_cost_ledger for real cost
    data instead of relying on the sparse event payload (cost_allocations was an
    integer count, not actual money amounts).  Also updates costo_promedio for
    each non-waste output product before posting the GL entries.

    GL entries posted:
      1. Raw material consumption (raw_material_cost > 0):
           Debe:  7001-costo-materia-prima-consumida
           Haber: 1201-inventario-materia-prima
      2. Finished goods creation (finished_goods_cost > 0):
           Debe:  1202-inventario-productos-terminados
           Haber: 7002-costo-produccion-valor-agregado
      3. Waste expense (waste_cost > 0):
           Debe:  7003-costo-merma-produccion
           Haber: 1201-inventario-materia-prima

    Errors are logged but do NOT re-raise — production is already committed.
    """

    def __init__(self, finance_service, db=None):
        self._finance = finance_service
        self._db      = db

    def handle(self, payload: Dict[str, Any]) -> None:
        if not self._finance or not hasattr(self._finance, "registrar_asiento"):
            return

        batch_id    = payload.get("batch_id", "")
        folio       = str(payload.get("folio", batch_id))
        sucursal_id = int(payload.get("sucursal_id", payload.get("branch_id", 1)))

        raw_cost      = 0.0
        finished_cost = 0.0
        waste_cost    = 0.0

        # ── 1. Prefer normalized payload costs (FASE 8) ───────────────────────
        # make_produccion_completada_payload() always includes a "costs" dict.
        # If the publisher computed real values, use them directly.
        costs_in_payload = payload.get("costs")
        if isinstance(costs_in_payload, dict):
            raw_cost      = float(costs_in_payload.get("raw_material_cost", 0))
            finished_cost = float(costs_in_payload.get("finished_goods_cost", 0))
            waste_cost    = float(costs_in_payload.get("waste_cost", 0))

        # ── 2. DB fallback: batch path when payload costs are zero ────────────
        # Handles the case where the event was published before FASE 8 or the
        # publisher could not compute costs (e.g. no precio_compra on the product).
        if raw_cost <= 0 and finished_cost <= 0 and waste_cost <= 0:
            if self._db and batch_id:
                try:
                    from core.services.finance.production_cost_service import (
                        ProductionCostService,
                    )
                    svc     = ProductionCostService(self._db)
                    summary = svc.compute_batch_costs(batch_id)
                    raw_cost      = summary.raw_material_cost
                    finished_cost = summary.finished_goods_cost
                    waste_cost    = summary.waste_cost
                    sucursal_id   = summary.branch_id
                    logger.debug(
                        "ProductionFinanceHandler: cost from DB batch=%s "
                        "raw=%.4f finished=%.4f waste=%.4f",
                        batch_id, raw_cost, finished_cost, waste_cost,
                    )
                except Exception as exc:
                    logger.warning(
                        "ProductionFinanceHandler: DB cost query failed batch=%s: %s",
                        batch_id, exc,
                    )

        # ── 3. Legacy fallback: old-style cost_allocations dict in payload ────
        if raw_cost <= 0 and finished_cost <= 0 and waste_cost <= 0:
            cost_allocs = payload.get("cost_allocations")
            if isinstance(cost_allocs, dict):
                raw_cost      = float(cost_allocs.get("raw_material_cost", 0))
                finished_cost = float(cost_allocs.get("finished_goods_cost", 0))
                waste_cost    = float(cost_allocs.get("waste_cost", 0))

        # ── Update costo_promedio when DB is available (batch path) ──────────
        if self._db and batch_id and (raw_cost > 0 or finished_cost > 0):
            try:
                from core.services.finance.production_cost_service import (
                    ProductionCostService,
                )
                n = ProductionCostService(self._db).update_average_costs(batch_id)
                logger.debug(
                    "ProductionFinanceHandler: costo_promedio updated for %d products", n
                )
            except Exception as exc:
                logger.debug("ProductionFinanceHandler: update_average_costs skipped: %s", exc)

        if raw_cost <= 0 and finished_cost <= 0 and waste_cost <= 0:
            logger.debug(
                "ProductionFinanceHandler: no cost data for batch=%s — skip GL",
                batch_id,
            )
            return

        # ── Post GL entries ───────────────────────────────────────────────────
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

            if waste_cost > 0:
                self._finance.registrar_asiento(
                    debe         = "7003-costo-merma-produccion",
                    haber        = "1201-inventario-materia-prima",
                    concepto     = f"Merma en producción lote {folio}",
                    monto        = waste_cost,
                    modulo       = "produccion",
                    referencia_id= batch_id,
                    sucursal_id  = sucursal_id,
                    evento       = "PRODUCCION_COMPLETADA",
                    metadata     = {"batch_id": batch_id, "folio": folio},
                )

            logger.info(
                "ProductionFinanceHandler: GL posted batch=%s "
                "raw=%.2f finished=%.2f waste=%.2f",
                batch_id, raw_cost, finished_cost, waste_cost,
            )
        except Exception as exc:
            logger.warning("ProductionFinanceHandler.handle GL: %s", exc)

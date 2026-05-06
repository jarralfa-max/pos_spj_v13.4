# core/events/handlers/production_handler.py — Phase 3
"""
ProductionInventoryHandler — handles PRODUCTION_ITEMS_PROCESS.

OUT raw materials and IN derived products when production executes.
Registered by wiring.py at priority=100 (sync, inside transaction SAVEPOINT).
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

# core/events/handlers/transfer_handler.py — Phase 5
"""
TransferInventoryHandler — handles TRANSFER_ITEMS_PROCESS.

Applies inventory movements for inter-branch transfers:
  OUT origin branch  (delta < 0, movement_type=TRANSFER_OUT or TRANSFER_CANCEL)
  IN  dest   branch  (delta > 0, movement_type=TRANSFER_IN)

Supports multi-sucursal: each movement carries its own branch_id so a single
publish covers both the origin deduction and the destination addition.
Registered by wiring.py at priority=100 (sync, inside SAVEPOINT).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("spj.handlers.transfer")


class TransferInventoryHandler:
    """
    Subscribes to TRANSFER_ITEMS_PROCESS and routes each movement through
    InventoryEngine.process_movement(), respecting multi-sucursal branch IDs.

    Payload expected:
        conn          — active SAVEPOINT connection (for atomicity)
        transfer_id   — ID of the transfer record
        operation_id  — base idempotency key
        reference_type— "TRANSFER_DISPATCH" | "TRANSFER_RECEIVE" | "TRANSFER_CANCEL"
        user          — usuario triggering the operation
        movements     — list of:
            product_id    int
            delta         float  (negative = OUT, positive = IN)
            branch_id     int    (origin OR destination, per movement)
            movement_type str    "TRANSFER_OUT" | "TRANSFER_IN" | "TRANSFER_CANCEL"
            operation_id  str    (optional per-item override)
    """

    def __init__(self, inventory_engine):
        self._inv = inventory_engine

    def handle(self, payload: Dict[str, Any]) -> None:
        conn       = payload.get("conn")
        base_op_id = str(payload.get("operation_id", ""))
        ref_type   = str(payload.get("reference_type", "TRANSFER"))
        ref_id     = payload.get("transfer_id")

        for mov in payload.get("movements", []):
            delta = float(mov.get("delta", 0))
            if abs(delta) < 1e-9:
                continue

            branch_id = int(
                mov.get("branch_id", payload.get("branch_id", 1))
            )
            op_id = str(
                mov.get("operation_id")
                or f"{base_op_id}_{mov['product_id']}_{mov.get('movement_type', '')}"
            )

            try:
                self._inv.process_movement(
                    product_id    = str(mov["product_id"]),
                    branch_id     = branch_id,
                    quantity      = delta,
                    movement_type = str(mov.get("movement_type", "TRANSFER")),
                    operation_id  = op_id,
                    reference_id  = ref_id,
                    reference_type= ref_type,
                    conn          = conn,
                )
            except Exception as exc:
                logger.error(
                    "TransferInventoryHandler: product=%s delta=%.4f branch=%s: %s",
                    mov.get("product_id"), delta, branch_id, exc,
                )
                raise

"""CustomerReturnHandler (Inventory context) — canonical customer return inflow (§36).

Consumes a customer-return event and posts a SALE_RETURN movement to the canonical
ledger. Returned meat/perishables never go straight back to AVAILABLE: they enter
PENDING_INSPECTION by default (configurable), so Quality can intervene. Idempotent
by operation_id. Not live-wired until the INV-27 cutover.
"""

from __future__ import annotations

import logging

from backend.application.inventory.use_cases.post_inventory_movement import (
    PostInventoryMovementUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import InventoryStatus, MovementType

logger = logging.getLogger("spj.inventory.customer_return")


class CustomerReturnHandler:
    event_name = "CUSTOMER_RETURN_CONFIRMED"

    def __init__(self, connection,
                 use_case: PostInventoryMovementUseCase | None = None,
                 default_status: InventoryStatus = InventoryStatus.PENDING_INSPECTION) -> None:
        self._conn = connection
        self._uc = use_case or PostInventoryMovementUseCase()
        self._default_status = default_status

    def handle(self, payload: dict) -> None:
        operation_id = str(payload.get("operation_id") or payload.get("event_id") or "").strip()
        branch_id = str(payload.get("branch_id") or "").strip()
        warehouse_id = str(payload.get("warehouse_id") or branch_id).strip()
        lines = payload.get("lines") or []
        if not operation_id or not branch_id or not lines:
            logger.warning("customer return: payload incompleto; se ignora")
            return
        built = []
        for ln in lines:
            status = ln.get("to_status")
            to_status = (InventoryStatus(status) if status else self._default_status)
            built.append(InventoryMovementLine.create(
                product_id=str(ln["product_id"]), quantity=ln.get("quantity", 0),
                weight=ln.get("weight", 0), unit=ln.get("unit", "PZA"),
                lot_id=ln.get("lot_id"),
                to_location_id=ln.get("to_location_id") or ln.get("location_id"),
                to_status=to_status, reason_code=ln.get("reason_code")))
        movement = InventoryMovement.create(
            movement_type=MovementType.SALE_RETURN, branch_id=branch_id,
            warehouse_id=warehouse_id, source_module="sales",
            source_document_type="SALE_RETURN",
            source_document_id=str(payload.get("document_id") or ""),
            operation_id=operation_id,
            created_by_user_id=str(payload.get("user_id") or "system"), lines=built)
        result = self._uc.execute(self._conn, movement,
                                  actor_user_id=str(payload.get("user_id") or "system"))
        if not result.success:
            logger.error("customer return %s falló: %s", operation_id, result.message)
            raise RuntimeError(result.message)

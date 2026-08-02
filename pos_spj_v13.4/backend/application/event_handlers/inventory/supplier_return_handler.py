"""SupplierReturnHandler (Inventory context) — canonical return-to-supplier outflow.

Consumes a procurement return event (PURCHASE_RETURN_CREATED) and posts a
SUPPLIER_RETURN movement (a DECREASE) to the canonical ledger: stock physically
leaves the warehouse back to the supplier. Returns typically leave from a
non-sellable bucket (a rejected/quarantined lot), so the source status is taken
from the line (default AVAILABLE). Idempotent by the event's operation_id. NOT
live-wired until the INV-27 cutover.
"""

from __future__ import annotations

import logging

from backend.application.event_handlers.inventory._ingress import resolve_ingress
from backend.application.inventory.use_cases.post_inventory_movement import (
    PostInventoryMovementUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import InventoryStatus, MovementType

logger = logging.getLogger("spj.inventory.supplier_return")


class SupplierReturnHandler:
    event_name = "PURCHASE_RETURN_CREATED"

    def __init__(self, connection,
                 use_case: PostInventoryMovementUseCase | None = None) -> None:
        self._conn = connection
        self._uc = use_case or PostInventoryMovementUseCase()

    def handle(self, payload: dict) -> None:
        ingress, reason = resolve_ingress(payload)
        lines = payload.get("lines") or []
        if ingress is None or not lines:
            logger.warning("supplier return: payload inválido (%s); se ignora",
                           reason or "sin líneas")
            return
        user = ingress.actor_user_id
        document_id = str(payload.get("return_id") or ingress.document_id)

        built = []
        for ln in lines:
            product_id = str(ln.get("product_id") or "")
            if not product_id:
                continue
            status = ln.get("from_status")
            from_status = InventoryStatus(status) if status else InventoryStatus.AVAILABLE
            built.append(InventoryMovementLine.create(
                product_id=product_id, quantity=ln.get("quantity", 0),
                weight=ln.get("weight", 0), unit=ln.get("unit", "PZA"),
                lot_id=ln.get("lot_id"),
                from_location_id=ln.get("from_location_id") or ln.get("location_id"),
                from_status=from_status, unit_cost=ln.get("unit_cost"),
                reason_code=ln.get("reason_code")))
        if not built:
            return

        movement = InventoryMovement.create(
            movement_type=MovementType.SUPPLIER_RETURN, branch_id=ingress.branch_id,
            warehouse_id=ingress.warehouse_id, source_module="procurement",
            source_document_type="PURCHASE_RETURN", source_document_id=document_id,
            operation_id=ingress.operation_id, created_by_user_id=user, lines=built)
        result = self._uc.execute(self._conn, movement, actor_user_id=user)
        if not result.success and result.error_code != "PERMISSION_DENIED":
            logger.error("supplier return %s falló: %s", ingress.operation_id,
                         result.message)
            raise RuntimeError(result.message)

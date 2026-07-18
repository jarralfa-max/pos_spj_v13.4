"""SaleIssueHandler (Inventory context) — canonical POS→inventory outflow (§23).

Consumes a sale-confirmed event and posts a SALE_ISSUE movement to the canonical
ledger through PostInventoryMovementUseCase (never mutating stock inline). Sales
detects the need and confirms; Inventory owns the stock effect. Idempotent by the
event's operation_id (a replay short-circuits inside the use case).

NOT wired to the live bus yet: the legacy sale path still owns stock until the
INV-27 cutover, so wiring both would double-count. Ready to subscribe at cutover.
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
from backend.domain.inventory.enums import MovementType

logger = logging.getLogger("spj.inventory.sale_issue")


def _build_lines(lines: list[dict]) -> list[InventoryMovementLine]:
    built = []
    for ln in lines:
        built.append(InventoryMovementLine.create(
            product_id=str(ln["product_id"]),
            quantity=ln.get("quantity", 0), weight=ln.get("weight", 0),
            unit=ln.get("unit", "PZA"), lot_id=ln.get("lot_id"),
            from_location_id=ln.get("from_location_id") or ln.get("location_id"),
            reason_code=ln.get("reason_code")))
    return built


class SaleIssueHandler:
    event_name = "SALE_CONFIRMED"

    def __init__(self, connection,
                 use_case: PostInventoryMovementUseCase | None = None) -> None:
        self._conn = connection
        self._uc = use_case or PostInventoryMovementUseCase()

    def handle(self, payload: dict) -> None:
        operation_id = str(payload.get("operation_id") or payload.get("event_id") or "").strip()
        branch_id = str(payload.get("branch_id") or "").strip()
        warehouse_id = str(payload.get("warehouse_id") or branch_id).strip()
        lines = payload.get("lines") or []
        if not operation_id or not branch_id or not lines:
            logger.warning("sale issue: payload incompleto; se ignora")
            return
        movement = InventoryMovement.create(
            movement_type=MovementType.SALE_ISSUE, branch_id=branch_id,
            warehouse_id=warehouse_id, source_module="sales",
            source_document_type="SALE", source_document_id=str(payload.get("document_id") or ""),
            operation_id=operation_id, created_by_user_id=str(payload.get("user_id") or "system"),
            lines=_build_lines(lines))
        result = self._uc.execute(self._conn, movement,
                                  actor_user_id=str(payload.get("user_id") or "system"))
        if not result.success:
            logger.error("sale issue %s falló: %s", operation_id, result.message)
            raise RuntimeError(result.message)

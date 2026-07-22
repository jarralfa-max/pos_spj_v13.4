"""GoodsReceiptReversedHandler (Inventory context) — undo a canonical receipt.

Consumes GOODS_RECEIPT_REVERSED and reverses the PURCHASE_RECEIPT movement that
this receipt posted, by looking it up in the ledger by its source document
(GOODS_RECEIPT / document_id) and delegating to ReverseInventoryMovementUseCase.
The reversal projects the exact inverse balance effect (§6). Idempotent by the
reversal's own operation_id and a single-reversal guard in the use case. NOT
live-wired until the INV-27 cutover.
"""

from __future__ import annotations

import logging

from backend.application.inventory.use_cases.reverse_inventory_movement import (
    ReverseInventoryMovementUseCase,
)
from backend.domain.inventory.enums import MovementStatus
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)

logger = logging.getLogger("spj.inventory.goods_receipt_reversed")

_SOURCE_DOCUMENT_TYPE = "GOODS_RECEIPT"


class GoodsReceiptReversedHandler:
    event_name = "GOODS_RECEIPT_REVERSED"

    def __init__(self, connection,
                 use_case: ReverseInventoryMovementUseCase | None = None) -> None:
        self._conn = connection
        self._uc = use_case or ReverseInventoryMovementUseCase()

    def handle(self, payload: dict) -> None:
        operation_id = str(payload.get("operation_id") or payload.get("event_id") or "").strip()
        document_id = str(payload.get("goods_receipt_id") or payload.get("document_id") or "")
        if not operation_id or not document_id:
            logger.warning("goods receipt reversed: payload incompleto; se ignora")
            return
        with InventoryUnitOfWork(self._conn) as uow:
            movements = uow.ledger.list_for_document(_SOURCE_DOCUMENT_TYPE, document_id)
        target = next((m for m in movements
                       if m["status"] == MovementStatus.POSTED.value), None)
        if target is None:
            logger.info("goods receipt reversed: sin movimiento posteado para %s",
                        document_id)
            return
        reason = str(payload.get("reason") or "Reverso de recepción de compra")
        result = self._uc.execute(
            self._conn, movement_id=target["id"],
            operation_id=f"{operation_id}:reversal", actor_user_id=str(payload.get("user_id") or "system"),
            reason=reason)
        if not result.success and result.error_code not in ("PERMISSION_DENIED",
                                                            "ALREADY_REVERSED"):
            logger.error("goods receipt reversal %s falló: %s", operation_id,
                         result.message)
            raise RuntimeError(result.message)

"""CanonicalTransferInventoryHandler — the transfer flip (INV-27).

Replaces the legacy TransferInventoryHandler on the live TRANSFER_ITEMS_PROCESS
event. The live payload carries a flat ``movements`` list where each movement has
its OWN ``branch_id`` (origin or destination) and a signed ``delta``:

- ``delta < 0`` → **dispatch** from that branch (DECREASE) → TRANSFER_DISPATCH
- ``delta > 0`` → **receipt** into that branch (INCREASE) → TRANSFER_RECEIPT

It posts one canonical movement per (branch, direction) instead of the legacy
per-item ``InventoryEngine.process_movement``. All join the transfer transaction
(the outer flow owns the commit, via payload ``conn``), idempotent by derived
operation_id. Location convention = branch_id (matches the canonical backfill).
"""

from __future__ import annotations

import logging
from decimal import Decimal

from backend.application.inventory.use_cases.post_inventory_movement import (
    PostInventoryMovementUseCase,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import InventoryStatus, MovementType

logger = logging.getLogger("spj.inventory.transfer_bridge")


def _num(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


class CanonicalTransferInventoryHandler:
    """Subscribes to TRANSFER_ITEMS_PROCESS and posts canonical transfer legs."""

    event_name = "TRANSFER_ITEMS_PROCESS"

    def __init__(self, connection_provider,
                 use_case: PostInventoryMovementUseCase | None = None) -> None:
        self._conn = connection_provider
        self._uc = use_case or PostInventoryMovementUseCase()

    def handle(self, payload: dict) -> None:
        base_op = str(payload.get("operation_id") or payload.get("transfer_id") or "").strip()
        document_id = str(payload.get("transfer_id") or "")
        user = str(payload.get("user") or payload.get("usuario") or "transferencia")
        movements = payload.get("movements", [])
        if not base_op or not movements:
            logger.warning("transfer bridge: payload incompleto; se ignora")
            return

        conn = payload.get("conn") or self._conn()

        # Group lines by (branch, direction) so each branch leg is one movement.
        dispatch: dict[str, list[InventoryMovementLine]] = {}
        receipt: dict[str, list[InventoryMovementLine]] = {}
        for mov in movements:
            product_id = str(mov.get("product_id") or "")
            delta = _num(mov.get("delta", 0))
            branch_id = str(mov.get("branch_id") or payload.get("branch_id") or "")
            if not product_id or delta == 0 or not branch_id:
                continue
            if delta < 0:
                dispatch.setdefault(branch_id, []).append(InventoryMovementLine.create(
                    product_id=product_id, quantity=-delta,
                    from_location_id=branch_id, from_status=InventoryStatus.AVAILABLE,
                    reason_code="TRANSFER_DISPATCH"))
            else:
                receipt.setdefault(branch_id, []).append(InventoryMovementLine.create(
                    product_id=product_id, quantity=delta,
                    to_location_id=branch_id, to_status=InventoryStatus.AVAILABLE,
                    reason_code="TRANSFER_RECEIPT"))

        for branch_id, lines in dispatch.items():
            self._post(conn, MovementType.TRANSFER_DISPATCH, lines,
                       operation_id=f"{base_op}:dispatch:{branch_id}", branch_id=branch_id,
                       document_id=document_id, user=user)
        for branch_id, lines in receipt.items():
            self._post(conn, MovementType.TRANSFER_RECEIPT, lines,
                       operation_id=f"{base_op}:receipt:{branch_id}", branch_id=branch_id,
                       document_id=document_id, user=user)

    def _post(self, conn, movement_type, lines, *, operation_id, branch_id,
              document_id, user) -> None:
        movement = InventoryMovement.create(
            movement_type=movement_type, branch_id=branch_id, warehouse_id=branch_id,
            source_module="transfers", source_document_type="TRANSFER",
            source_document_id=document_id, operation_id=operation_id,
            created_by_user_id=user, lines=lines)
        # Joins the transfer transaction; the outer flow owns the commit.
        result = self._uc.execute(conn, movement, actor_user_id=user,
                                  owns_transaction=False)
        if not result.success:
            raise RuntimeError(result.message or "No se pudo aplicar el movimiento de transferencia.")

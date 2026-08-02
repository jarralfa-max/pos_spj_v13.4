"""Lot quality → physical bucket projection (§9.1 / §9.2).

A lot's quality status is not just metadata: it dictates which physical balance
bucket its stock lives in. Changing the quality status must MOVE the lot's stock
between buckets (via STATUS_TRANSFER movements) so availability excludes a
blocked/quarantined lot and restores it on release. Both the manual quality use
case (§9.1) and the cold-chain auto-block (§9.2) share this projection, always
inside the caller's ``InventoryUnitOfWork`` (atomic with the status change).
"""

from __future__ import annotations

from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import (
    InventoryStatus,
    LotQualityStatus,
    MovementType,
)
from backend.application.inventory.services.movement_posting import post_movement
from backend.infrastructure.db.repositories.inventory.base import to_decimal

# Cada estado de calidad del lote corresponde a un *bucket físico* del balance.
PHYSICAL_BUCKET = {
    LotQualityStatus.RELEASED: InventoryStatus.AVAILABLE,
    LotQualityStatus.PENDING_INSPECTION: InventoryStatus.AVAILABLE,
    LotQualityStatus.BLOCKED: InventoryStatus.QUALITY_BLOCKED,
    LotQualityStatus.REJECTED: InventoryStatus.QUALITY_BLOCKED,
    LotQualityStatus.QUARANTINED: InventoryStatus.QUARANTINED,
}


def project_lot_quality_transition(uow, lot, new_status: LotQualityStatus, *,
                                   actor_user_id: str, base_op: str) -> int:
    """Move every balance of ``lot`` from its current quality bucket to the bucket
    of ``new_status`` with STATUS_TRANSFER movements. No-op (returns 0) when both
    map to the same bucket. Returns the number of balance lines moved."""
    from_bucket = PHYSICAL_BUCKET[lot.quality_status]
    to_bucket = PHYSICAL_BUCKET[new_status]
    if from_bucket is to_bucket:
        return 0
    moved = 0
    for row in uow.balances.list_by_lot(lot.product_id, lot.id):
        if row["inventory_status"] != from_bucket.value:
            continue
        qty = to_decimal(row["quantity"])
        wgt = to_decimal(row["weight"])
        if qty == 0 and wgt == 0:
            continue
        loc = row["location_id"] or row["warehouse_id"]
        mtype = (MovementType.QUALITY_RELEASE
                 if to_bucket is InventoryStatus.AVAILABLE
                 else MovementType.QUALITY_BLOCK)
        line = InventoryMovementLine.create(
            product_id=lot.product_id, quantity=qty, weight=wgt, lot_id=lot.id,
            from_location_id=loc, to_location_id=loc,
            from_status=from_bucket, to_status=to_bucket,
            reason_code="LOT_QUALITY")
        movement = InventoryMovement.create(
            movement_type=mtype, branch_id=row["branch_id"],
            warehouse_id=row["warehouse_id"], source_module="inventory",
            source_document_type="LOT_QUALITY", source_document_id=lot.id,
            operation_id=f"{base_op}:{moved}", created_by_user_id=actor_user_id,
            lines=[line])
        post_movement(uow, movement, actor_user_id=actor_user_id)
        moved += 1
    return moved

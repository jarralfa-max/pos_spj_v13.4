"""Lot use cases (INV-7): register a lot, block/release its quality status.

Registering is idempotent by (product_id, lot_code): a replay returns the
existing lot instead of colliding. Quality block/release gate on the granular
LOT_BLOCK / LOT_RELEASE permissions and emit the canonical lot events.
"""

from __future__ import annotations

import json

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.application.inventory.services.movement_posting import post_movement
from backend.domain.inventory.entities.inventory_lot import InventoryLot
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import (
    InventoryStatus,
    LotOrigin,
    LotQualityStatus,
    MovementType,
)
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.exceptions import (
    BranchScopeError,
    InventoryDomainError,
    InventoryPermissionDeniedError,
    LotNotFoundError,
)
from backend.infrastructure.db.repositories.inventory.base import to_decimal
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)

# §9.1: cada estado de calidad del lote corresponde a un *bucket físico* del
# balance. Bloquear/liberar un lote debe MOVER el stock entre buckets (no sólo
# tocar inventory_lots.quality_status), para que la disponibilidad lo excluya.
_PHYSICAL_BUCKET = {
    LotQualityStatus.RELEASED: InventoryStatus.AVAILABLE,
    LotQualityStatus.PENDING_INSPECTION: InventoryStatus.AVAILABLE,
    LotQualityStatus.BLOCKED: InventoryStatus.QUALITY_BLOCKED,
    LotQualityStatus.REJECTED: InventoryStatus.QUALITY_BLOCKED,
    LotQualityStatus.QUARANTINED: InventoryStatus.QUARANTINED,
}


def _project_lot_quality_transfer(uow, lot, *, from_bucket, to_bucket, actor_user_id,
                                  base_op) -> int:
    """Mueve todo el stock del lote de `from_bucket` a `to_bucket` con movimientos
    de transferencia de estado (§9.1). Devuelve el número de líneas movidas."""
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


def _emit(uow, event_name, *, operation_id, lot, actor_user_id):
    payload = build_event_payload(
        event_name, operation_id=operation_id, entity_id=lot.id,
        product_id=lot.product_id, lot_id=lot.id, branch_id=lot.branch_id,
        user_id=actor_user_id)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                       payload_json=json.dumps(payload), operation_id=operation_id)


class RegisterInventoryLotUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy.permissive_for_tests()

    def execute(self, connection, *, product_id: str, lot_code: str,
                origin_type: LotOrigin, operation_id: str, actor_user_id: str,
                context: InventoryExecutionContext | None = None,
                **lot_fields) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.LOT_CREATE)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
        # §5.3: los lotes son a nivel de sucursal — se valida el alcance de la
        # sucursal cuando se provee (el lote no lleva almacén).
        if context is not None and lot_fields.get("branch_id"):
            try:
                context.enforce_branch(lot_fields["branch_id"])
            except BranchScopeError as exc:
                return InventoryResult.fail(str(exc), "SCOPE_DENIED",
                                            operation_id=operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                existing = uow.lots.get_by_code(product_id, lot_code)
                if existing is not None:
                    return InventoryResult.ok("Lote ya registrado (idempotente)",
                                              entity_id=existing.id,
                                              operation_id=operation_id,
                                              already_processed=True)
                lot = InventoryLot.create(product_id=product_id, lot_code=lot_code,
                                          origin_type=origin_type, **lot_fields)
                uow.lots.save(lot)
                uow.audit.record(entity_type="LOT", entity_id=lot.id, action="CREATED",
                                 user_id=actor_user_id, operation_id=operation_id,
                                 product_id=product_id, lot_id=lot.id)
                _emit(uow, InventoryEvents.INVENTORY_LOT_CREATED,
                      operation_id=operation_id, lot=lot, actor_user_id=actor_user_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=operation_id)
        return InventoryResult.ok("Lote registrado", entity_id=lot.id,
                                  operation_id=operation_id)


class SetLotQualityStatusUseCase:
    """Block (quarantine/reject) or release a lot's quality status (§31)."""

    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy.permissive_for_tests()

    def execute(self, connection, *, lot_id: str, new_status: LotQualityStatus,
                operation_id: str, actor_user_id: str, reason: str = "",
                context: InventoryExecutionContext | None = None) -> InventoryResult:
        releasing = new_status is LotQualityStatus.RELEASED
        permission = (InventoryPermissions.LOT_RELEASE if releasing
                      else InventoryPermissions.LOT_BLOCK)
        event = (InventoryEvents.INVENTORY_LOT_RELEASED if releasing
                 else InventoryEvents.INVENTORY_LOT_BLOCKED)
        try:
            self._auth.require(actor_user_id, permission)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                lot = uow.lots.get(lot_id)
                if lot is None:
                    return InventoryResult.fail("Lote no encontrado", "LOT_NOT_FOUND",
                                                operation_id=operation_id)
                # §5.3: alcance validado contra la sucursal real del lote.
                if context is not None and lot.branch_id:
                    try:
                        context.enforce_branch(lot.branch_id)
                    except BranchScopeError as exc:
                        return InventoryResult.fail(str(exc), "SCOPE_DENIED",
                                                    operation_id=operation_id)
                # §9.1: mover el stock del lote entre buckets físicos ANTES de cambiar
                # el estado de calidad (mismo UoW → atómico). from = bucket del estado
                # actual; to = bucket del nuevo estado. Si coinciden, no hay movimiento.
                from_bucket = _PHYSICAL_BUCKET[lot.quality_status]
                to_bucket = _PHYSICAL_BUCKET[new_status]
                if from_bucket is not to_bucket:
                    _project_lot_quality_transfer(
                        uow, lot, from_bucket=from_bucket, to_bucket=to_bucket,
                        actor_user_id=actor_user_id, base_op=operation_id)
                if releasing:
                    lot.release()
                else:
                    lot.block(status=new_status)
                uow.lots.set_quality_status(lot.id, lot.quality_status)
                uow.audit.record(entity_type="LOT", entity_id=lot.id,
                                 action=f"QUALITY_{lot.quality_status.value}",
                                 user_id=actor_user_id, operation_id=operation_id,
                                 reason=reason, product_id=lot.product_id, lot_id=lot.id)
                _emit(uow, event, operation_id=operation_id, lot=lot,
                      actor_user_id=actor_user_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=operation_id)
        return InventoryResult.ok(f"Lote {lot.quality_status.value}", entity_id=lot.id,
                                  operation_id=operation_id)

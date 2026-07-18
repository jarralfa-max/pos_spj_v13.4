"""Lot use cases (INV-7): register a lot, block/release its quality status.

Registering is idempotent by (product_id, lot_code): a replay returns the
existing lot instead of colliding. Quality block/release gate on the granular
LOT_BLOCK / LOT_RELEASE permissions and emit the canonical lot events.
"""

from __future__ import annotations

import json

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.domain.inventory.entities.inventory_lot import InventoryLot
from backend.domain.inventory.enums import LotOrigin, LotQualityStatus
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.exceptions import (
    InventoryDomainError,
    InventoryPermissionDeniedError,
    LotNotFoundError,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


def _emit(uow, event_name, *, operation_id, lot, actor_user_id):
    payload = build_event_payload(
        event_name, operation_id=operation_id, entity_id=lot.id,
        product_id=lot.product_id, lot_id=lot.id, branch_id=lot.branch_id,
        user_id=actor_user_id)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                       payload_json=json.dumps(payload), operation_id=operation_id)


class RegisterInventoryLotUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, product_id: str, lot_code: str,
                origin_type: LotOrigin, operation_id: str, actor_user_id: str,
                **lot_fields) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.LOT_CREATE)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
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
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, lot_id: str, new_status: LotQualityStatus,
                operation_id: str, actor_user_id: str, reason: str = "") -> InventoryResult:
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

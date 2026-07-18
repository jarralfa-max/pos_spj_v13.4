"""Quarantine use cases (INV-15): quarantine → release / dispose (§31).

Quarantining moves stock AVAILABLE → QUARANTINED (a STATUS_TRANSFER movement) so
it is no longer available; release moves it back; disposal issues it out of the
QUARANTINED bucket. Inventory keeps the status; Quality decides. Segregation: who
quarantines by quality may not release it (self-release forbidden by default).
"""

from __future__ import annotations

import json

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.application.inventory.services.movement_posting import post_movement
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.entities.quarantine import InventoryQuarantine
from backend.domain.inventory.enums import (
    InventoryStatus,
    MovementType,
    QuarantineReason,
)
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.exceptions import (
    InventoryDomainError,
    InventoryPermissionDeniedError,
    SegregationOfDutiesError,
)
from backend.domain.inventory.policies.segregation_of_duties_policy import (
    SegregationOfDutiesPolicy,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


def _fail(exc, operation_id):
    code = ("PERMISSION_DENIED" if isinstance(exc, InventoryPermissionDeniedError)
            else "SEGREGATION_OF_DUTIES" if isinstance(exc, SegregationOfDutiesError)
            else "INVENTORY_RULE_VIOLATION")
    return InventoryResult.fail(str(exc), code, operation_id=operation_id)


def _emit(uow, event_name, q, *, operation_id, actor_user_id):
    payload = build_event_payload(
        event_name, operation_id=operation_id, entity_id=q.id, product_id=q.product_id,
        lot_id=q.lot_id, branch_id=q.branch_id, warehouse_id=q.warehouse_id,
        user_id=actor_user_id)
    uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                       payload_json=json.dumps(payload), operation_id=operation_id)


def _status_transfer(uow, q, *, mtype, from_status, to_status, base_op, actor_user_id):
    loc = q.location_id or q.warehouse_id
    line = InventoryMovementLine.create(
        product_id=q.product_id, quantity=q.quantity, weight=q.weight, lot_id=q.lot_id,
        from_location_id=loc, to_location_id=loc, from_status=from_status,
        to_status=to_status, reason_code=q.reason.value)
    movement = InventoryMovement.create(
        movement_type=mtype, branch_id=q.branch_id, warehouse_id=q.warehouse_id,
        source_module="inventory", source_document_type="QUARANTINE",
        source_document_id=q.id, operation_id=base_op, created_by_user_id=actor_user_id,
        lines=[line])
    post_movement(uow, movement, actor_user_id=actor_user_id)


class QuarantineStockUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, product_id: str, branch_id: str, warehouse_id: str,
                reason: QuarantineReason, quantity, operation_id: str, actor_user_id: str,
                weight=0, location_id: str | None = None, lot_id: str | None = None,
                reason_note: str = "") -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.QUARANTINE_CREATE)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            q = InventoryQuarantine.create(
                product_id=product_id, branch_id=branch_id, warehouse_id=warehouse_id,
                reason=reason, quantity=quantity, weight=weight, location_id=location_id,
                lot_id=lot_id, reason_note=reason_note, created_by_user_id=actor_user_id)
            with InventoryUnitOfWork(connection) as uow:
                _status_transfer(uow, q, mtype=MovementType.QUARANTINE_ENTRY,
                                 from_status=InventoryStatus.AVAILABLE,
                                 to_status=InventoryStatus.QUARANTINED,
                                 base_op=f"{operation_id}:enter", actor_user_id=actor_user_id)
                uow.quarantines.save(q)
                uow.audit.record(entity_type="QUARANTINE", entity_id=q.id, action="OPENED",
                                 user_id=actor_user_id, operation_id=operation_id,
                                 reason=reason.value, product_id=product_id, lot_id=lot_id)
                _emit(uow, InventoryEvents.INVENTORY_QUARANTINED, q,
                      operation_id=operation_id, actor_user_id=actor_user_id)
        except InventoryDomainError as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok("Stock en cuarentena", entity_id=q.id,
                                  operation_id=operation_id)


class ReleaseQuarantineUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None,
                 *, self_release_forbidden: bool = True) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()
        self._segregation = SegregationOfDutiesPolicy()
        self._self_release_forbidden = self_release_forbidden

    def execute(self, connection, *, quarantine_id: str, operation_id: str,
                actor_user_id: str) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.QUARANTINE_RELEASE)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                q = uow.quarantines.get(quarantine_id)
                if q is None:
                    return InventoryResult.fail("Cuarentena no encontrada",
                                                "QUARANTINE_NOT_FOUND",
                                                operation_id=operation_id)
                self._segregation.enforce_quality_blocker_not_releaser(
                    q.created_by_user_id or "", actor_user_id,
                    self_release_forbidden=self._self_release_forbidden)
                _status_transfer(uow, q, mtype=MovementType.QUARANTINE_RELEASE,
                                 from_status=InventoryStatus.QUARANTINED,
                                 to_status=InventoryStatus.AVAILABLE,
                                 base_op=f"{operation_id}:release", actor_user_id=actor_user_id)
                q.release(user_id=actor_user_id)
                uow.quarantines.save(q)
                _emit(uow, InventoryEvents.INVENTORY_QUARANTINE_RELEASED, q,
                      operation_id=operation_id, actor_user_id=actor_user_id)
        except (InventoryDomainError, SegregationOfDutiesError) as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok("Cuarentena liberada", entity_id=quarantine_id,
                                  operation_id=operation_id)


class DisposeQuarantineUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, quarantine_id: str, operation_id: str,
                actor_user_id: str, reason: str = "") -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.DISPOSAL_AUTHORIZE)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                q = uow.quarantines.get(quarantine_id)
                if q is None:
                    return InventoryResult.fail("Cuarentena no encontrada",
                                                "QUARANTINE_NOT_FOUND",
                                                operation_id=operation_id)
                loc = q.location_id or q.warehouse_id
                line = InventoryMovementLine.create(
                    product_id=q.product_id, quantity=q.quantity, weight=q.weight,
                    lot_id=q.lot_id, from_location_id=loc,
                    from_status=InventoryStatus.QUARANTINED, reason_code=q.reason.value)
                movement = InventoryMovement.create(
                    movement_type=MovementType.EXPIRY_DISPOSAL, branch_id=q.branch_id,
                    warehouse_id=q.warehouse_id, source_module="inventory",
                    source_document_type="QUARANTINE_DISPOSAL", source_document_id=q.id,
                    operation_id=f"{operation_id}:dispose", created_by_user_id=actor_user_id,
                    lines=[line])
                post_movement(uow, movement, actor_user_id=actor_user_id)
                q.dispose(user_id=actor_user_id)
                uow.quarantines.save(q)
                uow.audit.record(entity_type="QUARANTINE", entity_id=q.id,
                                 action="DISPOSED", user_id=actor_user_id,
                                 operation_id=operation_id, reason=reason,
                                 product_id=q.product_id, lot_id=q.lot_id)
        except InventoryDomainError as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok("Cuarentena dispuesta", entity_id=quarantine_id,
                                  operation_id=operation_id)

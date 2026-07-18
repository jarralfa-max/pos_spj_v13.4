"""Adjustment use cases (INV-14): create → approve → post → reverse (§29).

Every adjustment carries a reason. Its magnitude is evaluated against the
configured limit: WITHIN → postable directly; REQUIRES_APPROVAL/EXCEEDS → needs an
approver (segregation: the creator may not approve). Posting splits the signed
deltas into ADJUSTMENT_IN / ADJUSTMENT_OUT movements on the ledger; a posted
adjustment is undone only by a reversal. An approved count variance becomes an
adjustment (CreateAdjustmentFromCount), closing the count loop.
"""

from __future__ import annotations

import json

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.application.inventory.services.movement_posting import post_movement
from backend.domain.inventory.entities.adjustment import (
    InventoryAdjustment,
    InventoryAdjustmentLine,
)
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import (
    AdjustmentReason,
    AdjustmentStatus,
    CountStatus,
    LimitDecision,
    MovementType,
)
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.exceptions import (
    InventoryDomainError,
    InventoryPermissionDeniedError,
    SegregationOfDutiesError,
)
from backend.domain.inventory.policies.inventory_limit_policy import InventoryLimitPolicy
from backend.domain.inventory.policies.segregation_of_duties_policy import (
    SegregationOfDutiesPolicy,
)
from backend.domain.inventory.value_objects.authorization_grant import AuthorizationGrant
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


def _fail(exc, operation_id):
    code = ("PERMISSION_DENIED" if isinstance(exc, InventoryPermissionDeniedError)
            else "SEGREGATION_OF_DUTIES" if isinstance(exc, SegregationOfDutiesError)
            else "INVENTORY_RULE_VIOLATION")
    return InventoryResult.fail(str(exc), code, operation_id=operation_id)


def _evaluate(uow, adjustment, actor_user_id) -> LimitDecision:
    limit = uow.limits.resolve(operation_kind="ADJUSTMENT", user_id=actor_user_id,
                               branch_id=adjustment.branch_id)
    return InventoryLimitPolicy().classify(adjustment.total_magnitude, limit)


def _post_deltas(uow, adjustment, *, base_op, actor_user_id, invert=False) -> None:
    pos, neg = [], []
    for line in adjustment.lines:
        q = line.quantity_delta * (-1 if invert else 1)
        w = line.weight_delta * (-1 if invert else 1)
        loc = line.location_id or adjustment.warehouse_id
        direction = q if q != 0 else w
        ml = InventoryMovementLine.create(
            product_id=line.product_id, quantity=abs(q), weight=abs(w), lot_id=line.lot_id,
            reason_code=adjustment.reason.value,
            to_location_id=loc if direction > 0 else None,
            from_location_id=loc if direction < 0 else None)
        (pos if direction > 0 else neg).append(ml)

    def _mv(mtype, lines, suffix):
        movement = InventoryMovement.create(
            movement_type=mtype, branch_id=adjustment.branch_id,
            warehouse_id=adjustment.warehouse_id, source_module="inventory",
            source_document_type="ADJUSTMENT", source_document_id=adjustment.id,
            operation_id=f"{base_op}:{suffix}", created_by_user_id=actor_user_id,
            lines=lines)
        post_movement(uow, movement, actor_user_id=actor_user_id)

    if pos:
        _mv(MovementType.ADJUSTMENT_IN, pos, "in")
    if neg:
        _mv(MovementType.ADJUSTMENT_OUT, neg, "out")


class CreateAdjustmentUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, folio: str, branch_id: str, warehouse_id: str,
                reason: AdjustmentReason, lines: list[dict], operation_id: str,
                actor_user_id: str, reason_note: str = "",
                source_count_id: str | None = None) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.ADJUSTMENT_CREATE)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            adjustment = InventoryAdjustment.create(
                folio=folio, branch_id=branch_id, warehouse_id=warehouse_id, reason=reason,
                reason_note=reason_note, source_count_id=source_count_id,
                created_by_user_id=actor_user_id,
                lines=[InventoryAdjustmentLine.create(
                    product_id=str(ln["product_id"]), quantity_delta=ln.get("quantity_delta", 0),
                    weight_delta=ln.get("weight_delta", 0), location_id=ln.get("location_id"),
                    lot_id=ln.get("lot_id")) for ln in lines])
            with InventoryUnitOfWork(connection) as uow:
                decision = _evaluate(uow, adjustment, actor_user_id)
                if decision is not LimitDecision.WITHIN:
                    adjustment.require_approval()
                uow.adjustments.save(adjustment)
                uow.audit.record(entity_type="ADJUSTMENT", entity_id=adjustment.id,
                                 action="CREATED", user_id=actor_user_id,
                                 operation_id=operation_id, reason=reason.value,
                                 branch_id=branch_id, warehouse_id=warehouse_id)
        except InventoryDomainError as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok("Ajuste creado", entity_id=adjustment.id,
                                  operation_id=operation_id, status=adjustment.status.value,
                                  requires_approval=decision is not LimitDecision.WITHIN)


class ApproveAdjustmentUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()
        self._segregation = SegregationOfDutiesPolicy()

    def execute(self, connection, *, adjustment_id: str, operation_id: str,
                actor_user_id: str, reason: str = "") -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.ADJUSTMENT_APPROVE)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                adjustment = uow.adjustments.get(adjustment_id)
                if adjustment is None:
                    return InventoryResult.fail("Ajuste no encontrado",
                                                "ADJUSTMENT_NOT_FOUND",
                                                operation_id=operation_id)
                self._segregation.enforce_adjustment_creator_not_self_approving(
                    adjustment.created_by_user_id or "", actor_user_id,
                    requires_approval=True)
                adjustment.approve(user_id=actor_user_id)
                uow.adjustments.save(adjustment)
                uow.authorization_log.record(AuthorizationGrant(
                    permission_code=InventoryPermissions.ADJUSTMENT_APPROVE,
                    requested_by=adjustment.created_by_user_id or "system",
                    authorized_by=actor_user_id, operation_id=operation_id,
                    reason=reason or adjustment.reason.value,
                    quantity=adjustment.total_magnitude))
        except (InventoryDomainError, SegregationOfDutiesError) as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok("Ajuste aprobado", entity_id=adjustment_id,
                                  operation_id=operation_id)


class PostAdjustmentUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, adjustment_id: str, operation_id: str,
                actor_user_id: str) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.ADJUSTMENT_POST)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                adjustment = uow.adjustments.get(adjustment_id)
                if adjustment is None:
                    return InventoryResult.fail("Ajuste no encontrado",
                                                "ADJUSTMENT_NOT_FOUND",
                                                operation_id=operation_id)
                if adjustment.status is AdjustmentStatus.POSTED:
                    return InventoryResult.ok("Ajuste ya posteado (idempotente)",
                                              entity_id=adjustment_id,
                                              operation_id=operation_id,
                                              already_processed=True)
                if adjustment.status is AdjustmentStatus.PENDING_APPROVAL:
                    return InventoryResult.fail("El ajuste requiere aprobación",
                                                "APPROVAL_REQUIRED",
                                                operation_id=operation_id)
                _post_deltas(uow, adjustment, base_op=operation_id,
                             actor_user_id=actor_user_id)
                adjustment.mark_posted()
                uow.adjustments.save(adjustment)
                payload = build_event_payload(
                    InventoryEvents.INVENTORY_ADJUSTMENT_POSTED, operation_id=operation_id,
                    entity_id=adjustment.id, branch_id=adjustment.branch_id,
                    warehouse_id=adjustment.warehouse_id, user_id=actor_user_id,
                    reason=adjustment.reason.value)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=InventoryEvents.INVENTORY_ADJUSTMENT_POSTED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
        except InventoryDomainError as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok("Ajuste posteado", entity_id=adjustment_id,
                                  operation_id=operation_id)


class ReverseAdjustmentUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, adjustment_id: str, operation_id: str,
                actor_user_id: str, reason: str = "") -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.ADJUSTMENT_REVERSE)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                adjustment = uow.adjustments.get(adjustment_id)
                if adjustment is None:
                    return InventoryResult.fail("Ajuste no encontrado",
                                                "ADJUSTMENT_NOT_FOUND",
                                                operation_id=operation_id)
                if adjustment.status is not AdjustmentStatus.POSTED:
                    return InventoryResult.fail("Solo un ajuste posteado puede reversarse",
                                                "NOT_POSTED", operation_id=operation_id)
                _post_deltas(uow, adjustment, base_op=operation_id,
                             actor_user_id=actor_user_id, invert=True)
                adjustment.mark_reversed()
                uow.adjustments.save(adjustment)
                uow.audit.record(entity_type="ADJUSTMENT", entity_id=adjustment.id,
                                 action="REVERSED", user_id=actor_user_id,
                                 operation_id=operation_id, reason=reason)
        except InventoryDomainError as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok("Ajuste reversado", entity_id=adjustment_id,
                                  operation_id=operation_id)


class CreateAdjustmentFromCountUseCase:
    """Turn an approved count's variances into a COUNT_VARIANCE adjustment (§27)."""

    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, count_id: str, folio: str, operation_id: str,
                actor_user_id: str) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, InventoryPermissions.ADJUSTMENT_CREATE)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                count = uow.counts.get(count_id)
                if count is None:
                    return InventoryResult.fail("Conteo no encontrado", "COUNT_NOT_FOUND",
                                                operation_id=operation_id)
                if count.status is not CountStatus.APPROVED:
                    return InventoryResult.fail("El conteo debe estar aprobado",
                                                "COUNT_NOT_APPROVED",
                                                operation_id=operation_id)
                lines = [InventoryAdjustmentLine.create(
                    product_id=cl.product_id, quantity_delta=cl.variance_quantity,
                    weight_delta=cl.variance_weight, location_id=cl.location_id,
                    lot_id=cl.lot_id, reason_code="COUNT_VARIANCE")
                    for cl in count.lines if cl.has_variance]
                if not lines:
                    return InventoryResult.ok("Conteo sin varianzas; no requiere ajuste",
                                              operation_id=operation_id)
                adjustment = InventoryAdjustment.create(
                    folio=folio, branch_id=count.branch_id, warehouse_id=count.warehouse_id,
                    reason=AdjustmentReason.COUNT_VARIANCE, source_count_id=count.id,
                    created_by_user_id=actor_user_id, lines=lines)
                if _evaluate(uow, adjustment, actor_user_id) is not LimitDecision.WITHIN:
                    adjustment.require_approval()
                uow.adjustments.save(adjustment)
                count.mark_posted()
                uow.counts.save(count)
        except InventoryDomainError as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok("Ajuste creado desde conteo", entity_id=adjustment.id,
                                  operation_id=operation_id, status=adjustment.status.value)

"""InspectReceiptUseCase (§34/P0-E) — release or block a receipt held for
inspection.

``PurchaseReceiptHandler`` can route a received line into the
``PENDING_INSPECTION`` physical bucket (via an explicit ``quality_hold`` flag
or, since P0-E, automatically when the product's own quality profile requires
it — see ``QualityProductConfigQueryService.inspection_required``). Until this
use case existed, nothing in the codebase could ever move that stock back out:
the lot-quality machinery (``SetLotQualityStatusUseCase``) operates on a
different bucket (a lot's default ``PENDING_INSPECTION`` quality status maps to
the *available* bucket, not this one — see ``lot_quality_projection.py``), so
it cannot find or release inspection-held stock. This closes that gap with the
same segregated status-transfer pattern quarantine/lot-quality already use:
the entire held balance (identified by its real ``inventory_balances.id``)
moves atomically to AVAILABLE (pass) or QUALITY_BLOCKED (fail).
"""

from __future__ import annotations

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.execution_context import InventoryExecutionContext
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.application.inventory.services.movement_posting import post_movement
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import InventoryStatus, MovementType
from backend.domain.inventory.exceptions import (
    BranchScopeError,
    InventoryDomainError,
    InventoryPermissionDeniedError,
    WarehouseScopeError,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


def _fail(exc, operation_id):
    code = ("PERMISSION_DENIED" if isinstance(exc, InventoryPermissionDeniedError)
            else "SCOPE_DENIED" if isinstance(exc, (BranchScopeError, WarehouseScopeError))
            else "INVENTORY_RULE_VIOLATION")
    return InventoryResult.fail(str(exc), code, operation_id=operation_id)


class InspectReceiptUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy.permissive_for_tests()

    def execute(self, connection, *, balance_id: str, passed: bool, operation_id: str,
                actor_user_id: str, reason: str = "",
                context: InventoryExecutionContext | None = None) -> InventoryResult:
        permission = (InventoryPermissions.QUALITY_RELEASE if passed
                      else InventoryPermissions.QUALITY_BLOCK)
        try:
            self._auth.require(actor_user_id, permission)
        except InventoryPermissionDeniedError as exc:
            return _fail(exc, operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                balance = uow.balances.get_by_id(balance_id)
                if balance is None:
                    return InventoryResult.fail("Existencia no encontrada",
                                                "BALANCE_NOT_FOUND",
                                                operation_id=operation_id)
                if balance.inventory_status is not InventoryStatus.PENDING_INSPECTION:
                    return InventoryResult.fail(
                        "La existencia no está pendiente de inspección",
                        "NOT_PENDING_INSPECTION", operation_id=operation_id)
                if context is not None:
                    try:
                        context.enforce_branch(balance.branch_id)
                        context.enforce_warehouse(balance.warehouse_id)
                    except (BranchScopeError, WarehouseScopeError) as exc:
                        return _fail(exc, operation_id)
                to_status = (InventoryStatus.AVAILABLE if passed
                            else InventoryStatus.QUALITY_BLOCKED)
                loc = balance.location_id or balance.warehouse_id
                line = InventoryMovementLine.create(
                    product_id=balance.product_id, quantity=balance.quantity,
                    weight=balance.weight, lot_id=balance.lot_id,
                    from_location_id=loc, to_location_id=loc,
                    from_status=InventoryStatus.PENDING_INSPECTION, to_status=to_status,
                    reason_code="INSPECTION")
                movement = InventoryMovement.create(
                    movement_type=(MovementType.QUALITY_RELEASE if passed
                                  else MovementType.QUALITY_BLOCK),
                    branch_id=balance.branch_id, warehouse_id=balance.warehouse_id,
                    source_module="inventory", source_document_type="INSPECTION",
                    source_document_id=balance.id, operation_id=operation_id,
                    created_by_user_id=actor_user_id, lines=[line])
                post_movement(uow, movement, actor_user_id=actor_user_id)
                uow.audit.record(
                    entity_type="INSPECTION", entity_id=balance.id,
                    action="PASSED" if passed else "REJECTED",
                    user_id=actor_user_id, operation_id=operation_id, reason=reason,
                    product_id=balance.product_id, branch_id=balance.branch_id,
                    warehouse_id=balance.warehouse_id)
        except InventoryDomainError as exc:
            return _fail(exc, operation_id)
        return InventoryResult.ok(
            "Inspección aprobada" if passed else "Inspección rechazada",
            entity_id=balance_id, operation_id=operation_id)

"""PostInventoryMovementUseCase — the single canonical write path for stock (§9).

Every stock change (receipt, issue, transfer leg, adjustment, status change …)
posts a movement here. Replaces the legacy direct mutations
(actualizar_stock/sumar_stock/restar_stock). The use case:

- re-validates the granular permission,
- is idempotent by operation_id (a replay returns the existing movement),
- validates the movement (MovementValidationPolicy),
- projects the balance (NegativeInventoryPolicy on decreases),
- persists ledger + balance + audit + outbox in one atomic UnitOfWork,
- enqueues INVENTORY_MOVEMENT_POSTED (dispatched post-commit).
"""

from __future__ import annotations

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.application.inventory.services.movement_posting import post_movement
from backend.domain.inventory.entities.inventory_movement import InventoryMovement
from backend.domain.inventory.exceptions import (
    InventoryDomainError,
    InventoryPermissionDeniedError,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


class PostInventoryMovementUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, movement: InventoryMovement, *,
                actor_user_id: str,
                permission_code: str = InventoryPermissions.MOVEMENT_CREATE,
                negative_allowed: bool = False, authorized: bool = False) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, permission_code)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=movement.operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                movement_id, already = post_movement(
                    uow, movement, actor_user_id=actor_user_id,
                    negative_allowed=negative_allowed, authorized=authorized)
                if already:
                    return InventoryResult.ok(
                        "Movimiento ya registrado (idempotente)", entity_id=movement_id,
                        operation_id=movement.operation_id, already_processed=True)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=movement.operation_id)
        return InventoryResult.ok("Movimiento posteado", entity_id=movement.id,
                                  operation_id=movement.operation_id)

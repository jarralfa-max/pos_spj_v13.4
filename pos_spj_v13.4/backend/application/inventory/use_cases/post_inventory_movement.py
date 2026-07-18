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

import json

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.application.inventory.services.inventory_projection_service import (
    InventoryProjectionService,
)
from backend.domain.inventory.entities.inventory_movement import InventoryMovement
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.exceptions import (
    InventoryDomainError,
    InventoryPermissionDeniedError,
)
from backend.domain.inventory.policies.movement_validation_policy import (
    MovementValidationPolicy,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


class PostInventoryMovementUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()
        self._validation = MovementValidationPolicy()

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
                existing = uow.ledger.find_by_operation_id(movement.operation_id)
                if existing is not None:
                    return InventoryResult.ok(
                        "Movimiento ya registrado (idempotente)",
                        entity_id=existing["id"], operation_id=movement.operation_id,
                        already_processed=True)

                self._validation.enforce_valid(movement)
                movement.post()

                InventoryProjectionService(uow).project_movement(
                    movement, negative_allowed=negative_allowed, authorized=authorized)

                uow.ledger.save(movement)
                uow.audit.record(
                    entity_type="MOVEMENT", entity_id=movement.id, action="POSTED",
                    user_id=actor_user_id, authorized_by=movement.authorized_by_user_id,
                    operation_id=movement.operation_id, branch_id=movement.branch_id,
                    warehouse_id=movement.warehouse_id,
                    product_id=movement.lines[0].product_id if movement.lines else None)
                self._emit(uow, InventoryEvents.INVENTORY_MOVEMENT_POSTED, movement,
                           actor_user_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=movement.operation_id)
        return InventoryResult.ok("Movimiento posteado", entity_id=movement.id,
                                  operation_id=movement.operation_id)

    def _emit(self, uow, event_name, movement, actor_user_id) -> None:
        payload = build_event_payload(
            event_name, operation_id=movement.operation_id, entity_id=movement.id,
            product_id=movement.lines[0].product_id if movement.lines else None,
            branch_id=movement.branch_id, warehouse_id=movement.warehouse_id,
            user_id=actor_user_id, movement_type=movement.movement_type.value)
        uow.outbox.enqueue(event_id=payload["event_id"], event_name=event_name,
                           payload_json=json.dumps(payload),
                           operation_id=movement.operation_id)

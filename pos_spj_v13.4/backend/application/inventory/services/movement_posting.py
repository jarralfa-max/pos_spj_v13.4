"""post_movement — the shared, single-transaction ledger write (§6, §9).

Both PostInventoryMovementUseCase and higher-level flows (transfers, adjustments,
counts) need to post a movement WITHIN an existing UnitOfWork so the stock effect
and the document state commit together. This helper is that core: idempotency
check, validation, projection (negative-inventory guarded), ledger persistence,
audit and the INVENTORY_MOVEMENT_POSTED event — all on the passed-in uow (it
never commits; the caller's UoW owns the boundary).
"""

from __future__ import annotations

import json

from backend.application.inventory.services.inventory_projection_service import (
    InventoryProjectionService,
)
from backend.domain.inventory.entities.inventory_movement import InventoryMovement
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.policies.movement_validation_policy import (
    MovementValidationPolicy,
)

_VALIDATION = MovementValidationPolicy()


def post_movement(uow, movement: InventoryMovement, *, actor_user_id: str,
                  negative_allowed: bool = False, authorized: bool = False,
                  emit: bool = True) -> tuple[str, bool]:
    """Post a movement inside ``uow``. Returns (movement_id, already_processed)."""
    existing = uow.ledger.find_by_operation_id(movement.operation_id)
    if existing is not None:
        return existing["id"], True

    _VALIDATION.enforce_valid(movement)
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
    if emit:
        payload = build_event_payload(
            InventoryEvents.INVENTORY_MOVEMENT_POSTED, operation_id=movement.operation_id,
            entity_id=movement.id,
            product_id=movement.lines[0].product_id if movement.lines else None,
            branch_id=movement.branch_id, warehouse_id=movement.warehouse_id,
            user_id=actor_user_id, movement_type=movement.movement_type.value)
        uow.outbox.enqueue(
            event_id=payload["event_id"],
            event_name=InventoryEvents.INVENTORY_MOVEMENT_POSTED,
            payload_json=json.dumps(payload), operation_id=movement.operation_id)
    return movement.id, False

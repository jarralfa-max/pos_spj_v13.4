"""RegisterWasteUseCase (INV-16) — classify a loss and record it (§30).

Losses are classified distinctly (never all lumped as "merma"): actual waste,
shrinkage, process loss, expiry, damage, quality rejection, condemnation,
disposal. Each actual loss posts a physical-exit movement (WASTE / SHRINKAGE /
EXPIRY_DISPOSAL) from the given status bucket and records a waste event that
Finance consumes for valuation (INVENTORY_WASTE_RECORDED). Theoretical waste is a
standard/expected loss recorded without a stock movement.

Disposal-class losses (expiry / disposal / condemnation) require the
disposal-authorization permission; the rest require MOVEMENT_CREATE.
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
from backend.domain.inventory.enums import (
    DISPOSAL_WASTE_TYPES,
    WASTE_MOVEMENT_TYPE,
    InventoryStatus,
    WasteType,
)
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.exceptions import (
    InventoryDomainError,
    InventoryPermissionDeniedError,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


class RegisterWasteUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, product_id: str, branch_id: str, warehouse_id: str,
                waste_type: WasteType, quantity, operation_id: str, actor_user_id: str,
                weight=0, location_id: str | None = None, lot_id: str | None = None,
                from_status: InventoryStatus = InventoryStatus.AVAILABLE,
                reason_note: str = "") -> InventoryResult:
        permission = (InventoryPermissions.DISPOSAL_AUTHORIZE
                      if waste_type in DISPOSAL_WASTE_TYPES
                      else InventoryPermissions.MOVEMENT_CREATE)
        try:
            self._auth.require(actor_user_id, permission)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                movement_id = None
                theoretical = waste_type is WasteType.THEORETICAL_WASTE
                if not theoretical:
                    loc = location_id or warehouse_id
                    line = InventoryMovementLine.create(
                        product_id=product_id, quantity=quantity, weight=weight,
                        lot_id=lot_id, from_location_id=loc, from_status=from_status,
                        reason_code=waste_type.value)
                    movement = InventoryMovement.create(
                        movement_type=WASTE_MOVEMENT_TYPE[waste_type], branch_id=branch_id,
                        warehouse_id=warehouse_id, source_module="inventory",
                        source_document_type="WASTE", source_document_id=operation_id,
                        operation_id=f"{operation_id}:waste",
                        created_by_user_id=actor_user_id, lines=[line])
                    movement_id, _ = post_movement(uow, movement, actor_user_id=actor_user_id)

                waste_id = uow.waste.record(
                    product_id=product_id, branch_id=branch_id, warehouse_id=warehouse_id,
                    waste_type=waste_type.value, quantity=quantity, weight=weight,
                    location_id=location_id, lot_id=lot_id, movement_id=movement_id,
                    is_theoretical=theoretical, reason_note=reason_note,
                    created_by_user_id=actor_user_id)

                payload = build_event_payload(
                    InventoryEvents.INVENTORY_WASTE_RECORDED, operation_id=operation_id,
                    entity_id=waste_id, product_id=product_id, lot_id=lot_id,
                    branch_id=branch_id, warehouse_id=warehouse_id, user_id=actor_user_id,
                    waste_type=waste_type.value, quantity=str(quantity),
                    weight=str(weight), is_theoretical=theoretical, movement_id=movement_id)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=InventoryEvents.INVENTORY_WASTE_RECORDED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
                uow.audit.record(entity_type="WASTE", entity_id=waste_id,
                                 action=waste_type.value, user_id=actor_user_id,
                                 operation_id=operation_id, reason=reason_note,
                                 product_id=product_id, lot_id=lot_id, branch_id=branch_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=operation_id)
        return InventoryResult.ok(f"Merma registrada ({waste_type.value})",
                                  entity_id=waste_id, operation_id=operation_id,
                                  movement_id=movement_id, is_theoretical=theoretical)

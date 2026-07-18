"""ReverseInventoryMovementUseCase — undo a posted movement (§6, §15).

A posted movement is immutable; it is corrected only by a REVERSAL that projects
the exact inverse of its balance effect and records a new ledger entry linked via
``reversal_of_id``. Idempotent by the reversal's own operation_id; a movement can
only be reversed once.
"""

from __future__ import annotations

import json

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.application.inventory.result import InventoryResult
from backend.application.inventory.services.inventory_projection_service import (
    InventoryProjectionService,
    _line_from_row,
)
from backend.domain.inventory.entities.inventory_movement import InventoryMovement
from backend.domain.inventory.enums import MovementStatus, MovementType
from backend.domain.inventory.events import InventoryEvents, build_event_payload
from backend.domain.inventory.exceptions import (
    InventoryDomainError,
    InventoryPermissionDeniedError,
)
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)


class ReverseInventoryMovementUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()

    def execute(self, connection, *, movement_id: str, operation_id: str,
                actor_user_id: str, reason: str,
                permission_code: str = InventoryPermissions.MOVEMENT_REVERSE) -> InventoryResult:
        try:
            self._auth.require(actor_user_id, permission_code)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
        try:
            with InventoryUnitOfWork(connection) as uow:
                if uow.ledger.find_by_operation_id(operation_id) is not None:
                    return InventoryResult.ok("Reverso ya registrado (idempotente)",
                                              operation_id=operation_id,
                                              already_processed=True)
                original = uow.ledger.get(movement_id)
                if original is None:
                    return InventoryResult.fail("Movimiento no encontrado",
                                                "MOVEMENT_NOT_FOUND",
                                                operation_id=operation_id)
                if original["status"] == MovementStatus.REVERSED.value:
                    return InventoryResult.fail("El movimiento ya fue reversado",
                                                "ALREADY_REVERSED",
                                                operation_id=operation_id)

                original_type = MovementType(original["movement_type"])
                line_rows = uow.ledger.get_lines(movement_id)

                # 1) project the inverse effect onto balances
                InventoryProjectionService(uow).project_reversal(
                    branch_id=original["branch_id"],
                    warehouse_id=original["warehouse_id"],
                    original_movement_type=original_type, original_line_rows=line_rows)

                # 2) record the reversal movement + mark the original reversed
                reversal = InventoryMovement.create(
                    movement_type=MovementType.REVERSAL, branch_id=original["branch_id"],
                    warehouse_id=original["warehouse_id"], source_module="inventory",
                    source_document_type="REVERSAL", source_document_id=movement_id,
                    operation_id=operation_id, created_by_user_id=actor_user_id,
                    lines=[_line_from_row(r) for r in line_rows],
                    reversal_of_id=movement_id)
                reversal.post()
                uow.ledger.save(reversal)
                uow.ledger.mark_reversed(movement_id)
                uow.audit.record(
                    entity_type="MOVEMENT", entity_id=movement_id, action="REVERSED",
                    user_id=actor_user_id, operation_id=operation_id, reason=reason,
                    branch_id=original["branch_id"], warehouse_id=original["warehouse_id"])
                payload = build_event_payload(
                    InventoryEvents.INVENTORY_MOVEMENT_REVERSED, operation_id=operation_id,
                    entity_id=reversal.id, branch_id=original["branch_id"],
                    warehouse_id=original["warehouse_id"], user_id=actor_user_id,
                    reversal_of_id=movement_id)
                uow.outbox.enqueue(
                    event_id=payload["event_id"],
                    event_name=InventoryEvents.INVENTORY_MOVEMENT_REVERSED,
                    payload_json=json.dumps(payload), operation_id=operation_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVENTORY_RULE_VIOLATION",
                                        operation_id=operation_id)
        return InventoryResult.ok("Movimiento reversado", entity_id=reversal.id,
                                  operation_id=operation_id)

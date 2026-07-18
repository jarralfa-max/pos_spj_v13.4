"""MovementValidationPolicy — structural invariants of a movement (§15).

Every posted movement must carry a source document + operation_id (no orphan
movements, no silent adjustments), at least one line, and lines whose
location/status fields are consistent with the movement's balance direction.
Balance math itself is the balance service's job (INV-6).
"""

from __future__ import annotations

from backend.domain.inventory.enums import (
    MovementDirection,
    movement_direction,
)
from backend.domain.inventory.entities.inventory_movement import InventoryMovement
from backend.domain.inventory.exceptions import InventoryDomainError


class MovementValidationPolicy:
    def enforce_valid(self, movement: InventoryMovement) -> None:
        self._enforce_envelope(movement)
        direction = movement_direction(movement.movement_type)
        for line in movement.lines:
            self._enforce_line(direction, line)

    def _enforce_envelope(self, movement: InventoryMovement) -> None:
        required = {
            "source_module": movement.source_module,
            "source_document_type": movement.source_document_type,
            "source_document_id": movement.source_document_id,
            "operation_id": movement.operation_id,
            "branch_id": movement.branch_id,
            "warehouse_id": movement.warehouse_id,
            "created_by_user_id": movement.created_by_user_id,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise InventoryDomainError(
                f"Movimiento sin documento origen / metadatos: {', '.join(missing)}")
        if not movement.lines:
            raise InventoryDomainError("Un movimiento requiere al menos una línea")

    def _enforce_line(self, direction: MovementDirection, line) -> None:
        if direction is MovementDirection.INCREASE:
            if not line.to_location_id:
                raise InventoryDomainError(
                    "Un movimiento de entrada requiere ubicación destino")
        elif direction is MovementDirection.DECREASE:
            if not line.from_location_id:
                raise InventoryDomainError(
                    "Un movimiento de salida requiere ubicación origen")
        elif direction is MovementDirection.STATUS_TRANSFER:
            if line.from_status is None or line.to_status is None:
                raise InventoryDomainError(
                    "Un cambio de estado requiere estado origen y destino")
            if line.from_status == line.to_status:
                raise InventoryDomainError(
                    "El cambio de estado requiere estados distintos")
        # VARIANCE and MIXED lines are validated by their specific use cases.

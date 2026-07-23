"""CanonicalInventoryRepository — INV-27 corte: reemplaza al repositorio legacy
(inventory_stock / inventory_movements) que usa InventoryApplicationService, sin
cambiar su contrato (InventoryRepository). Todas las mutaciones postean al ledger
canónico vía post_movement; las lecturas de existencia vienen de la proyección
canónica (inventory_balances).

Implementa la misma interfaz que
``backend.infrastructure.db.repositories.inventory_repository.InventoryRepository``
(get_stock / get_movement / record_movement / commit / rollback) y devuelve los
mismos dataclasses, de modo que InventoryApplicationService y todos sus
consumidores (register/adjust use-cases, inventario.py, receive_po) quedan
migrados con solo cambiar la inyección en el composition root.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.inventory.queries import InventoryAvailabilityQueryService
from backend.application.inventory.services.movement_posting import post_movement
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.enums import InventoryStatus, MovementType
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)
from backend.infrastructure.db.repositories.inventory_repository import (
    InventoryMovementRecord,
    InventoryStockRecord,
)

# legacy movement_type string → (canonical MovementType, is_increase)
_TYPE_MAP = {
    "INCREASE": (MovementType.ADJUSTMENT_IN, True),
    "ADJUST_INCREASE": (MovementType.ADJUSTMENT_IN, True),
    "DECREASE": (MovementType.ADJUSTMENT_OUT, False),
    "ADJUST_DECREASE": (MovementType.ADJUSTMENT_OUT, False),
    "TRANSFER_OUT": (MovementType.TRANSFER_DISPATCH, False),
    "TRANSFER_IN": (MovementType.TRANSFER_RECEIPT, True),
}


class CanonicalInventoryRepository:
    """Ledger-backed drop-in for the legacy InventoryRepository interface."""

    def __init__(self, connection) -> None:
        self._connection = connection

    @property
    def connection(self):
        return self._connection

    # ── reads ────────────────────────────────────────────────────────────────
    def get_stock(self, product_id: str, branch_id: str) -> InventoryStockRecord:
        available = InventoryAvailabilityQueryService(self._connection).get_availability(
            product_id=str(product_id), branch_id=str(branch_id)).available
        return InventoryStockRecord(
            product_id=str(product_id), branch_id=str(branch_id),
            quantity=float(available), unit="unit", updated_at=None)

    def get_movement(self, *, operation_id: str, product_id: str, branch_id: str,
                     movement_type: str) -> InventoryMovementRecord | None:
        key = self._op_key(operation_id, movement_type)
        row = self._connection.execute(
            "SELECT id FROM inventory_ledger WHERE operation_id = ?", (key,)).fetchone()
        if row is None:
            return None
        # Idempotent replay: the exact numbers are not needed by callers beyond a
        # truthy hit; report the current available as stock_after.
        current = self.get_stock(product_id, branch_id).quantity
        return InventoryMovementRecord(
            operation_id=operation_id, product_id=str(product_id),
            branch_id=str(branch_id), movement_type=movement_type, quantity=0.0,
            stock_before=current, stock_after=current, unit="unit",
            source_module="inventory")

    # ── writes ───────────────────────────────────────────────────────────────
    def record_movement(self, movement: InventoryMovementRecord) -> InventoryMovementRecord:
        mapped = _TYPE_MAP.get(movement.movement_type)
        if mapped is None:
            raise ValueError(f"INVENTORY_UNSUPPORTED_MOVEMENT_TYPE: {movement.movement_type}")
        canonical_type, is_increase = mapped
        branch = str(movement.branch_id)
        qty = Decimal(str(movement.quantity))
        if is_increase:
            line = InventoryMovementLine.create(
                product_id=str(movement.product_id), quantity=qty,
                unit=movement.unit or "unit", to_location_id=branch,
                to_status=InventoryStatus.AVAILABLE,
                reason_code=(movement.reason or movement.movement_type)[:64])
        else:
            line = InventoryMovementLine.create(
                product_id=str(movement.product_id), quantity=qty,
                unit=movement.unit or "unit", from_location_id=branch,
                from_status=InventoryStatus.AVAILABLE,
                reason_code=(movement.reason or movement.movement_type)[:64])
        canonical = InventoryMovement.create(
            movement_type=canonical_type, branch_id=branch, warehouse_id=branch,
            source_module=movement.source_module or "inventory",
            source_document_type=movement.reference_type or movement.movement_type,
            source_document_id=str(movement.reference_id or movement.operation_id),
            operation_id=self._op_key(movement.operation_id, movement.movement_type),
            created_by_user_id=movement.user_name or "system", lines=[line])
        uow = InventoryUnitOfWork(self._connection, owns_transaction=False)
        post_movement(uow, canonical, actor_user_id=movement.user_name or "system")
        return movement

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        rollback = getattr(self._connection, "rollback", None)
        if rollback is not None:
            rollback()

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _op_key(operation_id: str, movement_type: str) -> str:
        # Canonical operation_id is UNIQUE; a transfer reuses one operation_id for
        # both legs, so we namespace by movement_type to keep them distinct.
        return f"{operation_id}:{movement_type}"

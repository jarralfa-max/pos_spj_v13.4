"""InventoryProjectionService — project a ledger movement onto balances (§9, §14).

Given a posted movement, it updates the ``inventory_balances`` projection per line
according to the movement's balance direction, enforcing the negative-inventory
policy on decreases. The balance is always a function of the ledger, so a
reversal projects the exact inverse of the original movement's effect.

This lives in the application layer (it reads/writes balances via the UoW); the
sign/direction rules come from the domain (``MOVEMENT_DIRECTION``).
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.inventory.enums import (
    InventoryStatus,
    MovementDirection,
    MovementType,
    movement_direction,
)
from backend.domain.inventory.entities.inventory_balance import InventoryBalance
from backend.domain.inventory.entities.inventory_movement import (
    InventoryMovement,
    InventoryMovementLine,
)
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.domain.inventory.policies.negative_inventory_policy import (
    NegativeInventoryPolicy,
)
from backend.infrastructure.db.repositories.inventory.base import to_decimal
from backend.shared.ids import new_uuid


def _status(value, default=InventoryStatus.AVAILABLE) -> InventoryStatus:
    if value is None or value == "":
        return default
    return value if isinstance(value, InventoryStatus) else InventoryStatus(value)


class InventoryProjectionService:
    def __init__(self, uow) -> None:
        self._uow = uow
        self._negative = NegativeInventoryPolicy()

    # ── public API ─────────────────────────────────────────────────────────
    def project_movement(self, movement: InventoryMovement, *,
                         negative_allowed: bool = False,
                         authorized: bool = False) -> None:
        direction = movement_direction(movement.movement_type)
        for line in movement.lines:
            self._project_line(movement, line, direction,
                               negative_allowed=negative_allowed, authorized=authorized)

    def project_reversal(self, *, branch_id: str, warehouse_id: str,
                         original_movement_type: MovementType,
                         original_line_rows: list[dict]) -> None:
        """Apply the exact inverse of the original movement's balance effect.

        A reversal is an authorized correction, so it may drive a bucket negative
        (e.g. reversing a receipt whose stock was already issued)."""
        direction = movement_direction(original_movement_type)
        for row in original_line_rows:
            line = _line_from_row(row)
            self._project_line(
                _FakeMovement(branch_id, warehouse_id), line, direction,
                negative_allowed=True, authorized=True, invert=True)

    # ── internals ──────────────────────────────────────────────────────────
    def _project_line(self, movement, line: InventoryMovementLine,
                      direction: MovementDirection, *, negative_allowed: bool,
                      authorized: bool, invert: bool = False) -> None:
        q = to_decimal(line.quantity)
        w = to_decimal(line.weight)
        sign = Decimal("-1") if invert else Decimal("1")

        if direction is MovementDirection.INCREASE:
            self._apply(movement, line, status=_status(line.to_status),
                        location_id=line.to_location_id, dq=sign * q, dw=sign * w,
                        negative_allowed=negative_allowed, authorized=authorized)
        elif direction is MovementDirection.DECREASE:
            self._apply(movement, line, status=_status(line.from_status),
                        location_id=line.from_location_id, dq=-sign * q, dw=-sign * w,
                        negative_allowed=negative_allowed, authorized=authorized)
        elif direction is MovementDirection.STATUS_TRANSFER:
            # remove from source bucket, add to destination bucket
            self._apply(movement, line, status=_status(line.from_status),
                        location_id=line.from_location_id or line.to_location_id,
                        dq=-sign * q, dw=-sign * w,
                        negative_allowed=negative_allowed, authorized=authorized)
            self._apply(movement, line, status=_status(line.to_status),
                        location_id=line.to_location_id or line.from_location_id,
                        dq=sign * q, dw=sign * w,
                        negative_allowed=negative_allowed, authorized=authorized)
        else:
            raise InventoryDomainError(
                f"Proyección de balance no soportada para dirección {direction}"
                " (VARIANCE/MIXED se manejan en sus casos de uso específicos)")

    def _apply(self, movement, line, *, status: InventoryStatus,
               location_id, dq: Decimal, dw: Decimal, negative_allowed: bool,
               authorized: bool) -> None:
        balance = self._uow.balances.get(
            product_id=line.product_id, branch_id=movement.branch_id,
            warehouse_id=movement.warehouse_id, inventory_status=status,
            location_id=location_id, lot_id=line.lot_id, serial_id=line.serial_id)
        if balance is None:
            balance = InventoryBalance.empty(
                product_id=line.product_id, branch_id=movement.branch_id,
                warehouse_id=movement.warehouse_id, inventory_status=status,
                location_id=location_id, lot_id=line.lot_id, serial_id=line.serial_id)
        if dq < 0:
            self._negative.enforce_can_decrease(
                current_on_hand=balance.quantity, decrease_by=-dq,
                allowed=negative_allowed, authorized=authorized)
        if dw < 0:
            self._negative.enforce_can_decrease(
                current_on_hand=balance.weight, decrease_by=-dw,
                allowed=negative_allowed, authorized=authorized)
        balance.apply_delta(quantity=dq, weight=dw)
        self._uow.balances.upsert(balance)


class _FakeMovement:
    """Minimal movement context for reversal projection (branch + warehouse)."""

    def __init__(self, branch_id: str, warehouse_id: str) -> None:
        self.branch_id = branch_id
        self.warehouse_id = warehouse_id


def _line_from_row(row: dict) -> InventoryMovementLine:
    # Fresh id: this rebuilt line may be re-inserted as a reversal ledger line.
    return InventoryMovementLine(
        id=new_uuid(), product_id=row["product_id"],
        quantity=to_decimal(row["quantity"]), weight=to_decimal(row["weight"]),
        unit=row.get("unit", "PZA"), lot_id=row.get("lot_id"),
        serial_id=row.get("serial_id"), from_location_id=row.get("from_location_id"),
        to_location_id=row.get("to_location_id"),
        from_status=_status(row.get("from_status"), default=None) if row.get("from_status") else None,
        to_status=_status(row.get("to_status"), default=None) if row.get("to_status") else None,
        reason_code=row.get("reason_code"))

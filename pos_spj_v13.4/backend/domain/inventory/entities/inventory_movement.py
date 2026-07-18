"""InventoryMovement (+Line) — the ledger entry (§15).

The movement is the fundamental fact: the balance is a projection of the ledger
(§9). Every movement carries its source document and an ``operation_id`` for
idempotency; a posted movement is immutable and is undone only by a REVERSAL,
never edited or deleted. Quantities/weights are Decimal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.inventory.enums import (
    InventoryStatus,
    MovementStatus,
    MovementType,
)
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dec(value: Decimal | int | str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, bool) or isinstance(value, float):
        raise InventoryDomainError("No se permite float en cantidades/pesos")
    return Decimal(str(value))


@dataclass(slots=True)
class InventoryMovementLine:
    id: str
    product_id: str
    quantity: Decimal = Decimal("0")
    weight: Decimal = Decimal("0")
    unit: str = "PZA"
    lot_id: str | None = None
    serial_id: str | None = None
    from_location_id: str | None = None
    to_location_id: str | None = None
    from_status: InventoryStatus | None = None
    to_status: InventoryStatus | None = None
    unit_cost: Decimal | None = None
    reason_code: str | None = None

    @classmethod
    def create(cls, *, product_id: str, quantity=0, weight=0, unit: str = "PZA",
               lot_id: str | None = None, serial_id: str | None = None,
               from_location_id: str | None = None, to_location_id: str | None = None,
               from_status: InventoryStatus | None = None,
               to_status: InventoryStatus | None = None,
               unit_cost=None, reason_code: str | None = None) -> "InventoryMovementLine":
        if not product_id:
            raise InventoryDomainError("La línea de movimiento requiere producto")
        q, w = _dec(quantity), _dec(weight)
        if q < 0 or w < 0:
            raise InventoryDomainError("Cantidad y peso de línea deben ser no negativos")
        if q == 0 and w == 0:
            raise InventoryDomainError(
                "La línea debe mover una cantidad o un peso mayor que cero")
        return cls(id=new_uuid(), product_id=product_id, quantity=q, weight=w,
                   unit=unit, lot_id=lot_id, serial_id=serial_id,
                   from_location_id=from_location_id, to_location_id=to_location_id,
                   from_status=from_status, to_status=to_status,
                   unit_cost=(None if unit_cost is None else _dec(unit_cost)),
                   reason_code=reason_code)


@dataclass(slots=True)
class InventoryMovement:
    id: str
    movement_type: MovementType
    branch_id: str
    warehouse_id: str
    source_module: str
    source_document_type: str
    source_document_id: str
    operation_id: str
    created_by_user_id: str
    lines: list[InventoryMovementLine] = field(default_factory=list)
    authorized_by_user_id: str | None = None
    status: MovementStatus = MovementStatus.DRAFT
    occurred_at: str = field(default_factory=_utcnow)
    reversal_of_id: str | None = None

    @classmethod
    def create(cls, *, movement_type: MovementType, branch_id: str,
               warehouse_id: str, source_module: str, source_document_type: str,
               source_document_id: str, operation_id: str, created_by_user_id: str,
               lines: list[InventoryMovementLine] | None = None,
               authorized_by_user_id: str | None = None,
               reversal_of_id: str | None = None) -> "InventoryMovement":
        return cls(
            id=new_uuid(), movement_type=movement_type, branch_id=branch_id,
            warehouse_id=warehouse_id, source_module=source_module,
            source_document_type=source_document_type,
            source_document_id=source_document_id, operation_id=operation_id,
            created_by_user_id=created_by_user_id, lines=list(lines or []),
            authorized_by_user_id=authorized_by_user_id,
            reversal_of_id=reversal_of_id)

    def add_line(self, line: InventoryMovementLine) -> None:
        if self.status is not MovementStatus.DRAFT:
            raise InventoryDomainError(
                "No se pueden agregar líneas a un movimiento ya posteado")
        self.lines.append(line)

    def post(self) -> None:
        if self.status is MovementStatus.REVERSED:
            raise InventoryDomainError("Un movimiento reversado no puede postearse")
        if not self.lines:
            raise InventoryDomainError("Un movimiento requiere al menos una línea")
        self.status = MovementStatus.POSTED

    def mark_reversed(self) -> None:
        if self.status is not MovementStatus.POSTED:
            raise InventoryDomainError("Solo un movimiento posteado puede reversarse")
        self.status = MovementStatus.REVERSED

"""InventoryTransfer (+Line) — the single canonical transfer aggregate (§24-25).

Replaces the three legacy transfer tables. The lifecycle enforces §24: on dispatch
the origin leaves AVAILABLE and the quantity is IN_TRANSIT (held on the transfer);
the destination does NOT gain available stock until it is received. Received lines
capture accepted/rejected quantities and any difference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.inventory.enums import (
    TransferDifferenceType,
    TransferStatus,
)
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dec(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, bool) or isinstance(value, float):
        raise InventoryDomainError("No se permite float en transferencias")
    return Decimal(str(value))


@dataclass(slots=True)
class InventoryTransferLine:
    id: str
    product_id: str
    quantity: Decimal
    weight: Decimal = Decimal("0")
    unit: str = "PZA"
    lot_id: str | None = None
    dispatched_quantity: Decimal = Decimal("0")
    received_quantity: Decimal = Decimal("0")
    difference_type: TransferDifferenceType | None = None

    @classmethod
    def create(cls, *, product_id: str, quantity, weight=0, unit: str = "PZA",
               lot_id: str | None = None) -> "InventoryTransferLine":
        if not product_id:
            raise InventoryDomainError("La línea de transferencia requiere producto")
        q = _dec(quantity)
        if q <= 0:
            raise InventoryDomainError("La cantidad a transferir debe ser mayor que cero")
        return cls(id=new_uuid(), product_id=product_id, quantity=q, weight=_dec(weight),
                   unit=unit, lot_id=lot_id)

    @property
    def in_transit_quantity(self) -> Decimal:
        return self.dispatched_quantity - self.received_quantity


_TRANSITIONS = {
    TransferStatus.DRAFT: {TransferStatus.PENDING_APPROVAL, TransferStatus.CANCELLED},
    TransferStatus.PENDING_APPROVAL: {TransferStatus.APPROVED, TransferStatus.REJECTED,
                                      TransferStatus.CANCELLED},
    TransferStatus.APPROVED: {TransferStatus.PICKING, TransferStatus.CANCELLED},
    TransferStatus.PICKING: {TransferStatus.READY_TO_DISPATCH, TransferStatus.CANCELLED},
    TransferStatus.READY_TO_DISPATCH: {TransferStatus.IN_TRANSIT, TransferStatus.CANCELLED},
    TransferStatus.IN_TRANSIT: {TransferStatus.PARTIALLY_RECEIVED, TransferStatus.RECEIVED,
                                TransferStatus.WITH_DIFFERENCES},
    TransferStatus.PARTIALLY_RECEIVED: {TransferStatus.RECEIVED, TransferStatus.WITH_DIFFERENCES},
    TransferStatus.RECEIVED: {TransferStatus.CLOSED, TransferStatus.WITH_DIFFERENCES},
    TransferStatus.WITH_DIFFERENCES: {TransferStatus.CLOSED},
}


@dataclass(slots=True)
class InventoryTransfer:
    id: str
    folio: str
    origin_branch_id: str
    origin_warehouse_id: str
    destination_branch_id: str
    destination_warehouse_id: str
    status: TransferStatus = TransferStatus.DRAFT
    lines: list[InventoryTransferLine] = field(default_factory=list)
    created_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    dispatched_by_user_id: str | None = None
    received_by_user_id: str | None = None
    carrier: str | None = None
    dispatched_at: str | None = None
    received_at: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, folio: str, origin_branch_id: str, origin_warehouse_id: str,
               destination_branch_id: str, destination_warehouse_id: str,
               lines: list[InventoryTransferLine] | None = None,
               created_by_user_id: str | None = None) -> "InventoryTransfer":
        if origin_warehouse_id == destination_warehouse_id:
            raise InventoryDomainError("Origen y destino no pueden ser el mismo almacén")
        return cls(id=new_uuid(), folio=folio, origin_branch_id=origin_branch_id,
                   origin_warehouse_id=origin_warehouse_id,
                   destination_branch_id=destination_branch_id,
                   destination_warehouse_id=destination_warehouse_id,
                   lines=list(lines or []), created_by_user_id=created_by_user_id)

    def _to(self, new_status: TransferStatus) -> None:
        allowed = _TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise InventoryDomainError(
                f"Transición inválida {self.status.value} → {new_status.value}")
        self.status = new_status

    def submit(self) -> None:
        if not self.lines:
            raise InventoryDomainError("La transferencia requiere al menos una línea")
        self._to(TransferStatus.PENDING_APPROVAL)

    def approve(self, *, user_id: str) -> None:
        self._to(TransferStatus.APPROVED)
        self.approved_by_user_id = user_id

    def reject(self) -> None:
        self._to(TransferStatus.REJECTED)

    def start_picking(self) -> None:
        self._to(TransferStatus.PICKING)

    def ready(self) -> None:
        self._to(TransferStatus.READY_TO_DISPATCH)

    def dispatch(self, *, user_id: str, carrier: str | None = None) -> None:
        self._to(TransferStatus.IN_TRANSIT)
        self.dispatched_by_user_id = user_id
        self.carrier = carrier
        self.dispatched_at = _utcnow()
        for line in self.lines:
            line.dispatched_quantity = line.quantity

    def receive(self, *, user_id: str, received: dict[str, Decimal]) -> None:
        """Apply received quantities per line id; set status by whether it balances."""
        if self.status not in (TransferStatus.IN_TRANSIT,
                               TransferStatus.PARTIALLY_RECEIVED):
            raise InventoryDomainError(
                f"No se puede recibir una transferencia en estado {self.status.value}")
        any_difference = False
        fully = True
        for line in self.lines:
            qty = _dec(received.get(line.id, 0))
            line.received_quantity += qty
            if line.received_quantity < line.dispatched_quantity:
                fully = False
                line.difference_type = TransferDifferenceType.SHORT
                any_difference = True
            elif line.received_quantity > line.dispatched_quantity:
                line.difference_type = TransferDifferenceType.OVER
                any_difference = True
        self.received_by_user_id = user_id
        self.received_at = _utcnow()
        if any_difference:
            self.status = TransferStatus.WITH_DIFFERENCES
        elif fully:
            self.status = TransferStatus.RECEIVED
        else:
            self.status = TransferStatus.PARTIALLY_RECEIVED

    def cancel(self) -> None:
        self._to(TransferStatus.CANCELLED)

    def close(self) -> None:
        self._to(TransferStatus.CLOSED)

"""InventoryReservation / InventoryAllocation (§22).

A reservation does NOT move stock — it reduces available-to-promise for a while
and can be released. An allocation links a (confirmed) reservation to specific
lots/locations/quantities. Both are UUIDv7, Decimal-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.inventory.enums import (
    ACTIVE_RESERVATION_STATUSES,
    AllocationStatus,
    ReservationSource,
    ReservationStatus,
)
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dec(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, bool) or isinstance(value, float):
        raise InventoryDomainError("No se permite float en reservas")
    return Decimal(str(value))


@dataclass(slots=True)
class InventoryReservation:
    id: str
    product_id: str
    branch_id: str
    warehouse_id: str
    source: ReservationSource
    source_document_id: str
    operation_id: str
    quantity: Decimal = Decimal("0")
    weight: Decimal = Decimal("0")
    status: ReservationStatus = ReservationStatus.CONFIRMED
    location_id: str | None = None
    lot_id: str | None = None
    expires_at: str | None = None
    created_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, product_id: str, branch_id: str, warehouse_id: str,
               source: ReservationSource, source_document_id: str, operation_id: str,
               quantity=0, weight=0, **kwargs) -> "InventoryReservation":
        if not product_id or not branch_id or not warehouse_id:
            raise InventoryDomainError("La reserva requiere producto/sucursal/almacén")
        q, w = _dec(quantity), _dec(weight)
        if q < 0 or w < 0:
            raise InventoryDomainError("Cantidad/peso de reserva no negativos")
        if q == 0 and w == 0:
            raise InventoryDomainError("La reserva debe reservar cantidad o peso")
        return cls(id=new_uuid(), product_id=product_id, branch_id=branch_id,
                   warehouse_id=warehouse_id, source=source,
                   source_document_id=source_document_id, operation_id=operation_id,
                   quantity=q, weight=w, **kwargs)

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_RESERVATION_STATUSES

    def is_expired(self, *, now: str | None = None) -> bool:
        if not self.expires_at:
            return False
        return (now or _utcnow()) >= self.expires_at

    def release(self) -> None:
        if not self.is_active:
            raise InventoryDomainError(
                f"No se puede liberar una reserva en estado {self.status.value}")
        self.status = ReservationStatus.RELEASED

    def expire(self) -> None:
        self.status = ReservationStatus.EXPIRED

    def mark_allocated(self) -> None:
        self.status = ReservationStatus.ALLOCATED


@dataclass(slots=True)
class InventoryAllocation:
    id: str
    reservation_id: str
    quantity: Decimal = Decimal("0")
    weight: Decimal = Decimal("0")
    lot_id: str | None = None
    location_id: str | None = None
    status: AllocationStatus = AllocationStatus.ALLOCATED
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, reservation_id: str, quantity=0, weight=0,
               lot_id: str | None = None, location_id: str | None = None) -> "InventoryAllocation":
        return cls(id=new_uuid(), reservation_id=reservation_id, quantity=_dec(quantity),
                   weight=_dec(weight), lot_id=lot_id, location_id=location_id)

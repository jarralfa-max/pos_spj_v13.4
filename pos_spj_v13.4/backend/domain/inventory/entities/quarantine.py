"""InventoryQuarantine — quality hold on physical stock (§31).

Quarantined stock exists physically but is not available; it cannot be sold,
consumed or transferred without release. Inventory keeps the status; Quality
decides release, rejection or disposal. Decimal-only, UUIDv7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.inventory.enums import QuarantineReason, QuarantineStatus
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dec(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, bool) or isinstance(value, float):
        raise InventoryDomainError("No se permite float en cuarentena")
    return Decimal(str(value))


_TRANSITIONS = {
    QuarantineStatus.OPEN: {QuarantineStatus.UNDER_REVIEW, QuarantineStatus.RELEASED,
                            QuarantineStatus.REJECTED, QuarantineStatus.DISPOSED},
    QuarantineStatus.UNDER_REVIEW: {QuarantineStatus.RELEASED,
                                    QuarantineStatus.PARTIALLY_RELEASED,
                                    QuarantineStatus.REJECTED, QuarantineStatus.DISPOSED},
    QuarantineStatus.PARTIALLY_RELEASED: {QuarantineStatus.RELEASED,
                                          QuarantineStatus.REJECTED,
                                          QuarantineStatus.DISPOSED},
}


@dataclass(slots=True)
class InventoryQuarantine:
    id: str
    product_id: str
    branch_id: str
    warehouse_id: str
    reason: QuarantineReason
    quantity: Decimal = Decimal("0")
    weight: Decimal = Decimal("0")
    status: QuarantineStatus = QuarantineStatus.OPEN
    location_id: str | None = None
    lot_id: str | None = None
    reason_note: str = ""
    created_by_user_id: str | None = None
    resolved_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, product_id: str, branch_id: str, warehouse_id: str,
               reason: QuarantineReason, quantity=0, weight=0, **kwargs) -> "InventoryQuarantine":
        if not product_id or not branch_id or not warehouse_id:
            raise InventoryDomainError("La cuarentena requiere producto/sucursal/almacén")
        if not reason:
            raise InventoryDomainError("La cuarentena requiere un motivo")
        q, w = _dec(quantity), _dec(weight)
        if q <= 0 and w <= 0:
            raise InventoryDomainError("La cuarentena debe retener cantidad o peso")
        return cls(id=new_uuid(), product_id=product_id, branch_id=branch_id,
                   warehouse_id=warehouse_id, reason=reason, quantity=q, weight=w, **kwargs)

    @property
    def is_open(self) -> bool:
        return self.status in (QuarantineStatus.OPEN, QuarantineStatus.UNDER_REVIEW,
                               QuarantineStatus.PARTIALLY_RELEASED)

    def _to(self, new_status: QuarantineStatus) -> None:
        if new_status not in _TRANSITIONS.get(self.status, set()):
            raise InventoryDomainError(
                f"Transición inválida {self.status.value} → {new_status.value}")
        self.status = new_status

    def start_review(self) -> None:
        self._to(QuarantineStatus.UNDER_REVIEW)

    def release(self, *, user_id: str) -> None:
        self._to(QuarantineStatus.RELEASED)
        self.resolved_by_user_id = user_id

    def reject(self, *, user_id: str) -> None:
        self._to(QuarantineStatus.REJECTED)
        self.resolved_by_user_id = user_id

    def dispose(self, *, user_id: str) -> None:
        self._to(QuarantineStatus.DISPOSED)
        self.resolved_by_user_id = user_id

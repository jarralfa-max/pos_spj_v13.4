"""InventoryAdjustment (+Line) — authorized stock corrections (§29).

Every adjustment carries a reason (never a free adjustment) and signed deltas per
line (+ increase / − decrease). Sensitive adjustments require approval; a posted
adjustment is corrected only by a reversal. The magnitude drives the limit
evaluation (WITHIN / REQUIRES_APPROVAL / EXCEEDS).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.inventory.enums import AdjustmentReason, AdjustmentStatus
from backend.domain.inventory.exceptions import InventoryDomainError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dec(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, bool) or isinstance(value, float):
        raise InventoryDomainError("No se permite float en ajustes")
    return Decimal(str(value))


@dataclass(slots=True)
class InventoryAdjustmentLine:
    id: str
    product_id: str
    quantity_delta: Decimal = Decimal("0")
    weight_delta: Decimal = Decimal("0")
    location_id: str | None = None
    lot_id: str | None = None
    reason_code: str | None = None

    @classmethod
    def create(cls, *, product_id: str, quantity_delta=0, weight_delta=0,
               location_id: str | None = None, lot_id: str | None = None,
               reason_code: str | None = None) -> "InventoryAdjustmentLine":
        if not product_id:
            raise InventoryDomainError("La línea de ajuste requiere producto")
        q, w = _dec(quantity_delta), _dec(weight_delta)
        if q == 0 and w == 0:
            raise InventoryDomainError("La línea de ajuste debe mover cantidad o peso")
        return cls(id=new_uuid(), product_id=product_id, quantity_delta=q,
                   weight_delta=w, location_id=location_id, lot_id=lot_id,
                   reason_code=reason_code)


_TRANSITIONS = {
    AdjustmentStatus.DRAFT: {AdjustmentStatus.PENDING_APPROVAL, AdjustmentStatus.APPROVED,
                             AdjustmentStatus.POSTED, AdjustmentStatus.CANCELLED},
    AdjustmentStatus.PENDING_APPROVAL: {AdjustmentStatus.APPROVED,
                                        AdjustmentStatus.CANCELLED},
    AdjustmentStatus.APPROVED: {AdjustmentStatus.POSTED, AdjustmentStatus.CANCELLED},
    AdjustmentStatus.POSTED: {AdjustmentStatus.REVERSED},
}


@dataclass(slots=True)
class InventoryAdjustment:
    id: str
    folio: str
    branch_id: str
    warehouse_id: str
    reason: AdjustmentReason
    status: AdjustmentStatus = AdjustmentStatus.DRAFT
    lines: list[InventoryAdjustmentLine] = field(default_factory=list)
    reason_note: str = ""
    source_count_id: str | None = None
    created_by_user_id: str | None = None
    approved_by_user_id: str | None = None
    created_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, folio: str, branch_id: str, warehouse_id: str,
               reason: AdjustmentReason, lines: list[InventoryAdjustmentLine] | None = None,
               reason_note: str = "", source_count_id: str | None = None,
               created_by_user_id: str | None = None) -> "InventoryAdjustment":
        if not branch_id or not warehouse_id:
            raise InventoryDomainError("El ajuste requiere sucursal y almacén")
        if not reason:
            raise InventoryDomainError("El ajuste requiere un motivo")
        adj = cls(id=new_uuid(), folio=folio, branch_id=branch_id,
                  warehouse_id=warehouse_id, reason=reason, lines=list(lines or []),
                  reason_note=reason_note, source_count_id=source_count_id,
                  created_by_user_id=created_by_user_id)
        if not adj.lines:
            raise InventoryDomainError("El ajuste requiere al menos una línea")
        return adj

    @property
    def total_magnitude(self) -> Decimal:
        return sum((abs(l.quantity_delta) for l in self.lines), Decimal("0"))

    def _to(self, new_status: AdjustmentStatus) -> None:
        if new_status not in _TRANSITIONS.get(self.status, set()):
            raise InventoryDomainError(
                f"Transición inválida {self.status.value} → {new_status.value}")
        self.status = new_status

    def require_approval(self) -> None:
        self._to(AdjustmentStatus.PENDING_APPROVAL)

    def approve(self, *, user_id: str) -> None:
        self._to(AdjustmentStatus.APPROVED)
        self.approved_by_user_id = user_id

    def mark_posted(self) -> None:
        self._to(AdjustmentStatus.POSTED)

    def mark_reversed(self) -> None:
        self._to(AdjustmentStatus.REVERSED)

    def cancel(self) -> None:
        self._to(AdjustmentStatus.CANCELLED)

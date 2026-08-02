"""InventoryAvailabilityQueryService — the read the POS/Sales consult (§23).

Sales NEVER updates stock; it asks this service what is available to promise.
Availability is derived from the canonical ``inventory_balances`` projection:
available = on-hand(AVAILABLE) − reserved. §9.3: it also breaks the stock down
across every physical bucket (reserved, allocated, in-transit, quarantined,
quality-blocked, expired, damaged, …) so a caller can *explain* a shortage —
why stock exists but is not available to promise. Read-only; Decimal throughout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from backend.domain.inventory.enums import ON_HAND_STATUSES, InventoryStatus
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    to_decimal,
)

_Z = Decimal("0")


@dataclass(frozen=True, slots=True)
class AvailabilityDTO:
    product_id: str
    branch_id: str
    on_hand: Decimal = _Z            # cantidad en el bucket AVAILABLE (compat)
    reserved: Decimal = _Z
    available: Decimal = _Z          # AVAILABLE − reserved
    # §9.3 — desglose completo por bucket físico (para explicar un faltante)
    allocated: Decimal = _Z
    in_transit: Decimal = _Z
    pending_inspection: Decimal = _Z
    quarantined: Decimal = _Z
    blocked: Decimal = _Z            # QUALITY_BLOCKED
    damaged: Decimal = _Z
    expired: Decimal = _Z
    returned: Decimal = _Z
    production_hold: Decimal = _Z
    recall_hold: Decimal = _Z
    total_on_hand: Decimal = _Z      # suma de todos los buckets físicos (excl. DISPOSED)
    on_hand_weight: Decimal = _Z
    reserved_weight: Decimal = _Z
    available_weight: Decimal = _Z
    by_status: dict = field(default_factory=dict)

    def explain(self) -> dict:
        """Full breakdown of where the product's stock sits (§9.3). ``available``
        is what Sales can promise; the remaining buckets explain the rest."""
        return {
            "product_id": self.product_id,
            "branch_id": self.branch_id,
            "total_on_hand": self.total_on_hand,
            "available": self.available,
            "on_hand": self.on_hand,
            "reserved": self.reserved,
            "allocated": self.allocated,
            "in_transit": self.in_transit,
            "pending_inspection": self.pending_inspection,
            "quarantined": self.quarantined,
            "blocked": self.blocked,
            "damaged": self.damaged,
            "expired": self.expired,
            "returned": self.returned,
            "production_hold": self.production_hold,
            "recall_hold": self.recall_hold,
        }


#: status del balance → nombre del campo del DTO que acumula su cantidad.
_STATUS_FIELD = {
    InventoryStatus.ALLOCATED.value: "allocated",
    InventoryStatus.IN_TRANSIT.value: "in_transit",
    InventoryStatus.PENDING_INSPECTION.value: "pending_inspection",
    InventoryStatus.QUARANTINED.value: "quarantined",
    InventoryStatus.QUALITY_BLOCKED.value: "blocked",
    InventoryStatus.DAMAGED.value: "damaged",
    InventoryStatus.EXPIRED.value: "expired",
    InventoryStatus.RETURNED.value: "returned",
    InventoryStatus.PRODUCTION_HOLD.value: "production_hold",
    InventoryStatus.RECALL_HOLD.value: "recall_hold",
}
_ON_HAND_VALUES = frozenset(s.value for s in ON_HAND_STATUSES)


class InventoryAvailabilityQueryService(InventoryRepositoryBase):
    def get_availability(self, *, product_id: str, branch_id: str,
                         warehouse_id: str | None = None) -> AvailabilityDTO:
        sql = ("SELECT inventory_status, quantity, weight, reserved_quantity,"
               " reserved_weight FROM inventory_balances WHERE product_id=? AND branch_id=?")
        params: tuple = (product_id, branch_id)
        if warehouse_id:
            sql += " AND warehouse_id=?"
            params += (warehouse_id,)
        rows = self._query(sql, params)

        on_hand = reserved = total_on_hand = _Z
        on_hand_w = reserved_w = _Z
        buckets: dict[str, Decimal] = {name: _Z for name in _STATUS_FIELD.values()}
        by_status: dict[str, str] = {}
        for r in rows:
            status = r["inventory_status"]
            qty = to_decimal(r["quantity"])
            by_status[status] = str(to_decimal(by_status.get(status, "0")) + qty)
            if status in _ON_HAND_VALUES:
                total_on_hand += qty
            if status == InventoryStatus.AVAILABLE.value:
                on_hand += qty
                reserved += to_decimal(r["reserved_quantity"])
                on_hand_w += to_decimal(r["weight"])
                reserved_w += to_decimal(r["reserved_weight"])
            else:
                field_name = _STATUS_FIELD.get(status)
                if field_name is not None:
                    buckets[field_name] += qty

        return AvailabilityDTO(
            product_id=product_id, branch_id=branch_id, on_hand=on_hand,
            reserved=reserved, available=on_hand - reserved,
            total_on_hand=total_on_hand, on_hand_weight=on_hand_w,
            reserved_weight=reserved_w, available_weight=on_hand_w - reserved_w,
            by_status=by_status, **buckets)

    def is_available(self, *, product_id: str, branch_id: str, quantity,
                     warehouse_id: str | None = None) -> bool:
        dto = self.get_availability(product_id=product_id, branch_id=branch_id,
                                    warehouse_id=warehouse_id)
        return dto.available >= to_decimal(quantity)

    def available_at_warehouse(self, *, product_id: str, warehouse_id: str) -> Decimal:
        """Available-to-promise at a single warehouse regardless of branch —
        the surplus a replenishment transfer can draw from (§34)."""
        rows = self._query(
            "SELECT quantity, reserved_quantity FROM inventory_balances"
            " WHERE product_id=? AND warehouse_id=? AND inventory_status=?",
            (product_id, warehouse_id, InventoryStatus.AVAILABLE.value))
        available = Decimal("0")
        for r in rows:
            available += to_decimal(r["quantity"]) - to_decimal(r["reserved_quantity"])
        return available

"""InventoryAvailabilityQueryService — the read the POS/Sales consult (§23).

Sales NEVER updates stock; it asks this service what is available to promise.
Availability is derived from the canonical ``inventory_balances`` projection:
available = on-hand(AVAILABLE) − reserved. It also exposes the other buckets
(reserved, in-transit, quarantined, blocked) so callers can explain a shortage.
Read-only; Decimal throughout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from backend.domain.inventory.enums import InventoryStatus
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    to_decimal,
)


@dataclass(frozen=True, slots=True)
class AvailabilityDTO:
    product_id: str
    branch_id: str
    on_hand: Decimal = Decimal("0")
    reserved: Decimal = Decimal("0")
    available: Decimal = Decimal("0")
    on_hand_weight: Decimal = Decimal("0")
    reserved_weight: Decimal = Decimal("0")
    available_weight: Decimal = Decimal("0")
    by_status: dict = field(default_factory=dict)


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

        on_hand = reserved = Decimal("0")
        on_hand_w = reserved_w = Decimal("0")
        by_status: dict[str, str] = {}
        for r in rows:
            status = r["inventory_status"]
            qty = to_decimal(r["quantity"])
            by_status[status] = str(to_decimal(by_status.get(status, "0")) + qty)
            if status == InventoryStatus.AVAILABLE.value:
                on_hand += qty
                reserved += to_decimal(r["reserved_quantity"])
                on_hand_w += to_decimal(r["weight"])
                reserved_w += to_decimal(r["reserved_weight"])

        return AvailabilityDTO(
            product_id=product_id, branch_id=branch_id, on_hand=on_hand,
            reserved=reserved, available=on_hand - reserved, on_hand_weight=on_hand_w,
            reserved_weight=reserved_w, available_weight=on_hand_w - reserved_w,
            by_status=by_status)

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

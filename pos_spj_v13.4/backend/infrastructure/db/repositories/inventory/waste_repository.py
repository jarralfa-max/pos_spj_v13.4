"""WasteRepository — records classified loss events (§30)."""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    dec_str,
    now_iso,
)
from backend.shared.ids import new_uuid


class WasteRepository(InventoryRepositoryBase):
    def record(self, *, product_id: str, branch_id: str, warehouse_id: str,
               waste_type: str, quantity, weight=0, location_id: str | None = None,
               lot_id: str | None = None, movement_id: str | None = None,
               is_theoretical: bool = False, reason_note: str = "",
               created_by_user_id: str | None = None) -> str:
        row_id = new_uuid()
        self._execute(
            "INSERT INTO inventory_waste_event (id, product_id, branch_id, warehouse_id,"
            " location_id, lot_id, waste_type, quantity, weight, movement_id,"
            " is_theoretical, reason_note, created_by_user_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (row_id, product_id, branch_id, warehouse_id, location_id, lot_id, waste_type,
             dec_str(quantity), dec_str(weight), movement_id, 1 if is_theoretical else 0,
             reason_note, created_by_user_id, now_iso()))
        return row_id

    def list_for_product(self, product_id: str, branch_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM inventory_waste_event WHERE product_id=? AND branch_id=?"
            " ORDER BY created_at DESC", (product_id, branch_id))

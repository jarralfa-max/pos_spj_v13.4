"""AdjustmentRepository — persists inventory adjustments + lines (§29)."""

from __future__ import annotations

from backend.domain.inventory.entities.adjustment import (
    InventoryAdjustment,
    InventoryAdjustmentLine,
)
from backend.domain.inventory.enums import AdjustmentReason, AdjustmentStatus
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    dec_str,
    enum_value,
    to_decimal,
)


def _line(row: dict) -> InventoryAdjustmentLine:
    return InventoryAdjustmentLine(
        id=row["id"], product_id=row["product_id"],
        quantity_delta=to_decimal(row["quantity_delta"]),
        weight_delta=to_decimal(row["weight_delta"]), location_id=row["location_id"],
        lot_id=row["lot_id"], reason_code=row["reason_code"])


class AdjustmentRepository(InventoryRepositoryBase):
    def save(self, a: InventoryAdjustment) -> None:
        self._execute(
            "INSERT INTO inventory_adjustment (id, folio, branch_id, warehouse_id, reason,"
            " status, reason_note, source_count_id, created_by_user_id,"
            " approved_by_user_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " approved_by_user_id=excluded.approved_by_user_id",
            (a.id, a.folio, a.branch_id, a.warehouse_id, enum_value(a.reason),
             enum_value(a.status), a.reason_note, a.source_count_id,
             a.created_by_user_id, a.approved_by_user_id, a.created_at))
        for line in a.lines:
            self._execute(
                "INSERT INTO inventory_adjustment_line (id, adjustment_id, product_id,"
                " location_id, lot_id, quantity_delta, weight_delta, reason_code)"
                " VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                (line.id, a.id, line.product_id, line.location_id, line.lot_id,
                 dec_str(line.quantity_delta), dec_str(line.weight_delta),
                 line.reason_code))

    def get(self, adjustment_id: str) -> InventoryAdjustment | None:
        row = self._query_one("SELECT * FROM inventory_adjustment WHERE id=?",
                              (adjustment_id,))
        if row is None:
            return None
        lines = [_line(r) for r in self._query(
            "SELECT * FROM inventory_adjustment_line WHERE adjustment_id=? ORDER BY id",
            (adjustment_id,))]
        return InventoryAdjustment(
            id=row["id"], folio=row["folio"], branch_id=row["branch_id"],
            warehouse_id=row["warehouse_id"], reason=AdjustmentReason(row["reason"]),
            status=AdjustmentStatus(row["status"]), lines=lines,
            reason_note=row["reason_note"] or "", source_count_id=row["source_count_id"],
            created_by_user_id=row["created_by_user_id"],
            approved_by_user_id=row["approved_by_user_id"], created_at=row["created_at"])

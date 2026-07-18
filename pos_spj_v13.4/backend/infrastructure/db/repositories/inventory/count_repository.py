"""CountRepository — persists inventory counts + lines (§27-28)."""

from __future__ import annotations

from backend.domain.inventory.entities.count import (
    InventoryCount,
    InventoryCountLine,
)
from backend.domain.inventory.enums import CountStatus, CountType
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    dec_str,
    enum_value,
    to_decimal,
)


def _line(row: dict) -> InventoryCountLine:
    return InventoryCountLine(
        id=row["id"], product_id=row["product_id"], location_id=row["location_id"],
        lot_id=row["lot_id"], expected_quantity=to_decimal(row["expected_quantity"]),
        expected_weight=to_decimal(row["expected_weight"]),
        counted_quantity=to_decimal(row["counted_quantity"]),
        counted_weight=to_decimal(row["counted_weight"]),
        variance_quantity=to_decimal(row["variance_quantity"]),
        variance_weight=to_decimal(row["variance_weight"]),
        recount_count=int(row["recount_count"]), counted=bool(row["counted"]))


class CountRepository(InventoryRepositoryBase):
    def save(self, c: InventoryCount) -> None:
        self._execute(
            "INSERT INTO inventory_count (id, folio, count_type, branch_id, warehouse_id,"
            " status, blind, scope_location_id, scope_product_id, scope_lot_id,"
            " created_by_user_id, counted_by_user_id, approved_by_user_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " counted_by_user_id=excluded.counted_by_user_id,"
            " approved_by_user_id=excluded.approved_by_user_id",
            (c.id, c.folio, enum_value(c.count_type), c.branch_id, c.warehouse_id,
             enum_value(c.status), 1 if c.blind else 0, c.scope_location_id,
             c.scope_product_id, c.scope_lot_id, c.created_by_user_id,
             c.counted_by_user_id, c.approved_by_user_id, c.created_at))
        for line in c.lines:
            self._save_line(c.id, line)

    def _save_line(self, count_id: str, line: InventoryCountLine) -> None:
        self._execute(
            "INSERT INTO inventory_count_line (id, count_id, product_id, location_id,"
            " lot_id, expected_quantity, expected_weight, counted_quantity,"
            " counted_weight, variance_quantity, variance_weight, recount_count, counted)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET counted_quantity=excluded.counted_quantity,"
            " counted_weight=excluded.counted_weight,"
            " variance_quantity=excluded.variance_quantity,"
            " variance_weight=excluded.variance_weight,"
            " recount_count=excluded.recount_count, counted=excluded.counted",
            (line.id, count_id, line.product_id, line.location_id, line.lot_id,
             dec_str(line.expected_quantity), dec_str(line.expected_weight),
             dec_str(line.counted_quantity), dec_str(line.counted_weight),
             dec_str(line.variance_quantity), dec_str(line.variance_weight),
             line.recount_count, 1 if line.counted else 0))

    def get(self, count_id: str) -> InventoryCount | None:
        row = self._query_one("SELECT * FROM inventory_count WHERE id=?", (count_id,))
        if row is None:
            return None
        lines = [_line(r) for r in self._query(
            "SELECT * FROM inventory_count_line WHERE count_id=? ORDER BY id", (count_id,))]
        return InventoryCount(
            id=row["id"], folio=row["folio"], count_type=CountType(row["count_type"]),
            branch_id=row["branch_id"], warehouse_id=row["warehouse_id"],
            status=CountStatus(row["status"]), blind=bool(row["blind"]), lines=lines,
            scope_location_id=row["scope_location_id"],
            scope_product_id=row["scope_product_id"], scope_lot_id=row["scope_lot_id"],
            created_by_user_id=row["created_by_user_id"],
            counted_by_user_id=row["counted_by_user_id"],
            approved_by_user_id=row["approved_by_user_id"], created_at=row["created_at"])

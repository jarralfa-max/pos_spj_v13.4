"""TransferRepository — persists the transfer aggregate + lines (§24-25)."""

from __future__ import annotations

from backend.domain.inventory.entities.transfer import (
    InventoryTransfer,
    InventoryTransferLine,
)
from backend.domain.inventory.enums import TransferDifferenceType, TransferStatus
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    dec_str,
    enum_value,
    to_decimal,
)


def _line(row: dict) -> InventoryTransferLine:
    return InventoryTransferLine(
        id=row["id"], product_id=row["product_id"], quantity=to_decimal(row["quantity"]),
        weight=to_decimal(row["weight"]), unit=row["unit"], lot_id=row["lot_id"],
        dispatched_quantity=to_decimal(row["dispatched_quantity"]),
        received_quantity=to_decimal(row["received_quantity"]),
        difference_type=(TransferDifferenceType(row["difference_type"])
                         if row["difference_type"] else None))


class TransferRepository(InventoryRepositoryBase):
    def save(self, t: InventoryTransfer) -> None:
        self._execute(
            "INSERT INTO inventory_transfer (id, folio, origin_branch_id,"
            " origin_warehouse_id, destination_branch_id, destination_warehouse_id,"
            " status, created_by_user_id, approved_by_user_id, dispatched_by_user_id,"
            " received_by_user_id, carrier, dispatched_at, received_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " approved_by_user_id=excluded.approved_by_user_id,"
            " dispatched_by_user_id=excluded.dispatched_by_user_id,"
            " received_by_user_id=excluded.received_by_user_id, carrier=excluded.carrier,"
            " dispatched_at=excluded.dispatched_at, received_at=excluded.received_at",
            (t.id, t.folio, t.origin_branch_id, t.origin_warehouse_id,
             t.destination_branch_id, t.destination_warehouse_id, enum_value(t.status),
             t.created_by_user_id, t.approved_by_user_id, t.dispatched_by_user_id,
             t.received_by_user_id, t.carrier, t.dispatched_at, t.received_at, t.created_at))
        for line in t.lines:
            self._save_line(t.id, line)

    def _save_line(self, transfer_id: str, line: InventoryTransferLine) -> None:
        self._execute(
            "INSERT INTO inventory_transfer_line (id, transfer_id, product_id, lot_id,"
            " unit, quantity, weight, dispatched_quantity, received_quantity,"
            " difference_type) VALUES (?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET dispatched_quantity=excluded.dispatched_quantity,"
            " received_quantity=excluded.received_quantity,"
            " difference_type=excluded.difference_type",
            (line.id, transfer_id, line.product_id, line.lot_id, line.unit,
             dec_str(line.quantity), dec_str(line.weight),
             dec_str(line.dispatched_quantity), dec_str(line.received_quantity),
             enum_value(line.difference_type) if line.difference_type else None))

    def get(self, transfer_id: str) -> InventoryTransfer | None:
        row = self._query_one("SELECT * FROM inventory_transfer WHERE id=?", (transfer_id,))
        if row is None:
            return None
        lines = [_line(r) for r in self._query(
            "SELECT * FROM inventory_transfer_line WHERE transfer_id=? ORDER BY id",
            (transfer_id,))]
        return InventoryTransfer(
            id=row["id"], folio=row["folio"], origin_branch_id=row["origin_branch_id"],
            origin_warehouse_id=row["origin_warehouse_id"],
            destination_branch_id=row["destination_branch_id"],
            destination_warehouse_id=row["destination_warehouse_id"],
            status=TransferStatus(row["status"]), lines=lines,
            created_by_user_id=row["created_by_user_id"],
            approved_by_user_id=row["approved_by_user_id"],
            dispatched_by_user_id=row["dispatched_by_user_id"],
            received_by_user_id=row["received_by_user_id"], carrier=row["carrier"],
            dispatched_at=row["dispatched_at"], received_at=row["received_at"],
            created_at=row["created_at"])

    def list_by_status(self, status: TransferStatus) -> list[dict]:
        return self._query(
            "SELECT * FROM inventory_transfer WHERE status=? ORDER BY created_at",
            (enum_value(status),))

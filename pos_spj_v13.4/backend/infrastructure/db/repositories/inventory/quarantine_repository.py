"""QuarantineRepository — persists quality holds / quarantines (§31)."""

from __future__ import annotations

from backend.domain.inventory.entities.quarantine import InventoryQuarantine
from backend.domain.inventory.enums import QuarantineReason, QuarantineStatus
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    dec_str,
    enum_value,
    to_decimal,
)


class QuarantineRepository(InventoryRepositoryBase):
    def save(self, q: InventoryQuarantine) -> None:
        self._execute(
            "INSERT INTO inventory_quarantine (id, product_id, branch_id, warehouse_id,"
            " location_id, lot_id, reason, quantity, weight, status, reason_note,"
            " created_by_user_id, resolved_by_user_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " resolved_by_user_id=excluded.resolved_by_user_id",
            (q.id, q.product_id, q.branch_id, q.warehouse_id, q.location_id, q.lot_id,
             enum_value(q.reason), dec_str(q.quantity), dec_str(q.weight),
             enum_value(q.status), q.reason_note, q.created_by_user_id,
             q.resolved_by_user_id, q.created_at))

    def get(self, quarantine_id: str) -> InventoryQuarantine | None:
        row = self._query_one("SELECT * FROM inventory_quarantine WHERE id=?",
                              (quarantine_id,))
        if row is None:
            return None
        return InventoryQuarantine(
            id=row["id"], product_id=row["product_id"], branch_id=row["branch_id"],
            warehouse_id=row["warehouse_id"], reason=QuarantineReason(row["reason"]),
            quantity=to_decimal(row["quantity"]), weight=to_decimal(row["weight"]),
            status=QuarantineStatus(row["status"]), location_id=row["location_id"],
            lot_id=row["lot_id"], reason_note=row["reason_note"] or "",
            created_by_user_id=row["created_by_user_id"],
            resolved_by_user_id=row["resolved_by_user_id"], created_at=row["created_at"])

    def list_open(self, *, lot_id: str | None = None) -> list[dict]:
        if lot_id:
            return self._query(
                "SELECT * FROM inventory_quarantine WHERE status IN"
                " ('OPEN','UNDER_REVIEW','PARTIALLY_RELEASED') AND lot_id=?"
                " ORDER BY created_at", (lot_id,))
        return self._query(
            "SELECT * FROM inventory_quarantine WHERE status IN"
            " ('OPEN','UNDER_REVIEW','PARTIALLY_RELEASED') ORDER BY created_at")

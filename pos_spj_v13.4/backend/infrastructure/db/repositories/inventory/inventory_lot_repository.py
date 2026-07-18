"""InventoryLotRepository — persists lots and lists FEFO candidates (§19-20)."""

from __future__ import annotations

from backend.domain.inventory.entities.inventory_lot import InventoryLot
from backend.domain.inventory.enums import LotOrigin, LotQualityStatus
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    enum_value,
)


def _to_entity(row: dict) -> InventoryLot:
    return InventoryLot(
        id=row["id"], product_id=row["product_id"], lot_code=row["lot_code"],
        origin_type=LotOrigin(row["origin_type"]),
        quality_status=LotQualityStatus(row["quality_status"]),
        traceability_status=row["traceability_status"],
        supplier_lot_code=row["supplier_lot_code"],
        production_lot_code=row["production_lot_code"],
        slaughter_lot_code=row["slaughter_lot_code"],
        origin_document_id=row["origin_document_id"],
        production_date=row["production_date"], slaughter_date=row["slaughter_date"],
        expiration_date=row["expiration_date"], received_at=row["received_at"],
        branch_id=row["branch_id"], created_at=row["created_at"])


class InventoryLotRepository(InventoryRepositoryBase):
    def save(self, lot: InventoryLot) -> None:
        self._execute(
            "INSERT INTO inventory_lots (id, product_id, lot_code, origin_type,"
            " origin_document_id, supplier_lot_code, production_lot_code,"
            " slaughter_lot_code, production_date, slaughter_date, expiration_date,"
            " received_at, quality_status, traceability_status, branch_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (lot.id, lot.product_id, lot.lot_code, enum_value(lot.origin_type),
             lot.origin_document_id, lot.supplier_lot_code, lot.production_lot_code,
             lot.slaughter_lot_code, lot.production_date, lot.slaughter_date,
             lot.expiration_date, lot.received_at, enum_value(lot.quality_status),
             lot.traceability_status, lot.branch_id, lot.created_at))

    def get(self, lot_id: str) -> InventoryLot | None:
        row = self._query_one("SELECT * FROM inventory_lots WHERE id=?", (lot_id,))
        return _to_entity(row) if row else None

    def get_by_code(self, product_id: str, lot_code: str) -> InventoryLot | None:
        row = self._query_one(
            "SELECT * FROM inventory_lots WHERE product_id=? AND lot_code=?",
            (product_id, lot_code))
        return _to_entity(row) if row else None

    def list_for_product(self, product_id: str, *, branch_id: str | None = None) -> list[dict]:
        if branch_id:
            return self._query(
                "SELECT * FROM inventory_lots WHERE product_id=? AND branch_id=?"
                " ORDER BY expiration_date", (product_id, branch_id))
        return self._query(
            "SELECT * FROM inventory_lots WHERE product_id=? ORDER BY expiration_date",
            (product_id,))

    def set_quality_status(self, lot_id: str, status: LotQualityStatus) -> None:
        self._execute(
            "UPDATE inventory_lots SET quality_status=? WHERE id=?",
            (enum_value(status), lot_id))

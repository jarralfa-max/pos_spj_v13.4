"""ReservationRepository — persists reservations and their allocations (§22)."""

from __future__ import annotations

from backend.domain.inventory.entities.reservation import (
    InventoryAllocation,
    InventoryReservation,
)
from backend.domain.inventory.enums import (
    AllocationStatus,
    ReservationSource,
    ReservationStatus,
)
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    dec_str,
    enum_value,
    nz,
    to_decimal,
    zn,
)


def _to_reservation(row: dict) -> InventoryReservation:
    return InventoryReservation(
        id=row["id"], product_id=row["product_id"], branch_id=row["branch_id"],
        warehouse_id=row["warehouse_id"], source=ReservationSource(row["source"]),
        source_document_id=row["source_document_id"], operation_id=row["operation_id"],
        quantity=to_decimal(row["quantity"]), weight=to_decimal(row["weight"]),
        status=ReservationStatus(row["status"]), location_id=zn(row["location_id"]),
        lot_id=zn(row["lot_id"]), expires_at=row["expires_at"],
        created_by_user_id=row["created_by_user_id"], created_at=row["created_at"])


class ReservationRepository(InventoryRepositoryBase):
    def find_by_operation_id(self, operation_id: str) -> dict | None:
        return self._query_one(
            "SELECT * FROM inventory_reservation WHERE operation_id=?", (operation_id,))

    def get(self, reservation_id: str) -> InventoryReservation | None:
        row = self._query_one(
            "SELECT * FROM inventory_reservation WHERE id=?", (reservation_id,))
        return _to_reservation(row) if row else None

    def save(self, r: InventoryReservation) -> None:
        self._execute(
            "INSERT INTO inventory_reservation (id, product_id, branch_id, warehouse_id,"
            " location_id, lot_id, source, source_document_id, operation_id, quantity,"
            " weight, status, expires_at, created_by_user_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r.id, r.product_id, r.branch_id, r.warehouse_id, nz(r.location_id),
             nz(r.lot_id), enum_value(r.source), r.source_document_id, r.operation_id,
             dec_str(r.quantity), dec_str(r.weight), enum_value(r.status), r.expires_at,
             r.created_by_user_id, r.created_at))

    def update_status(self, reservation_id: str, status: ReservationStatus) -> None:
        self._execute("UPDATE inventory_reservation SET status=? WHERE id=?",
                      (enum_value(status), reservation_id))

    def list_active_for_product(self, product_id: str, branch_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM inventory_reservation WHERE product_id=? AND branch_id=?"
            " AND status IN ('PENDING','CONFIRMED','PARTIALLY_ALLOCATED','ALLOCATED',"
            "'PARTIALLY_FULFILLED') ORDER BY created_at", (product_id, branch_id))

    def save_allocation(self, a: InventoryAllocation) -> None:
        self._execute(
            "INSERT INTO inventory_allocation (id, reservation_id, lot_id, location_id,"
            " quantity, weight, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (a.id, a.reservation_id, a.lot_id, a.location_id, dec_str(a.quantity),
             dec_str(a.weight), enum_value(a.status), a.created_at))

    def list_allocations(self, reservation_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM inventory_allocation WHERE reservation_id=? ORDER BY created_at",
            (reservation_id,))

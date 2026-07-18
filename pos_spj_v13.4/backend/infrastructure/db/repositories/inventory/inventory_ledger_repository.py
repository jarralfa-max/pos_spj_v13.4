"""InventoryLedgerRepository — persists the movement ledger (§9, §15).

Writes ``inventory_ledger`` + ``inventory_ledger_lines`` atomically (the UoW owns
the commit). ``operation_id`` is UNIQUE, so ``find_by_operation_id`` is the
idempotency check every use case runs before posting a movement.
"""

from __future__ import annotations

from backend.domain.inventory.entities.inventory_movement import InventoryMovement
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    dec_str,
    enum_value,
    now_iso,
    opt_dec_str,
)


class InventoryLedgerRepository(InventoryRepositoryBase):
    def find_by_operation_id(self, operation_id: str) -> dict | None:
        return self._query_one(
            "SELECT id, movement_type, status, operation_id FROM inventory_ledger"
            " WHERE operation_id=?", (operation_id,))

    def get(self, movement_id: str) -> dict | None:
        return self._query_one(
            "SELECT * FROM inventory_ledger WHERE id=?", (movement_id,))

    def get_lines(self, movement_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM inventory_ledger_lines WHERE movement_id=? ORDER BY id",
            (movement_id,))

    def save(self, movement: InventoryMovement) -> None:
        self._execute(
            "INSERT INTO inventory_ledger (id, movement_type, branch_id, warehouse_id,"
            " source_module, source_document_type, source_document_id, operation_id,"
            " created_by_user_id, authorized_by_user_id, status, occurred_at,"
            " reversal_of_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (movement.id, enum_value(movement.movement_type), movement.branch_id,
             movement.warehouse_id, movement.source_module,
             movement.source_document_type, movement.source_document_id,
             movement.operation_id, movement.created_by_user_id,
             movement.authorized_by_user_id, enum_value(movement.status),
             movement.occurred_at, movement.reversal_of_id))
        for line in movement.lines:
            self._execute(
                "INSERT INTO inventory_ledger_lines (id, movement_id, product_id, lot_id,"
                " serial_id, quantity, weight, unit, from_location_id, to_location_id,"
                " from_status, to_status, unit_cost, reason_code)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (line.id, movement.id, line.product_id, line.lot_id, line.serial_id,
                 dec_str(line.quantity), dec_str(line.weight), line.unit,
                 line.from_location_id, line.to_location_id,
                 enum_value(line.from_status) if line.from_status else None,
                 enum_value(line.to_status) if line.to_status else None,
                 opt_dec_str(line.unit_cost), line.reason_code))

    def mark_reversed(self, movement_id: str) -> None:
        self._execute(
            "UPDATE inventory_ledger SET status='REVERSED', occurred_at=occurred_at"
            " WHERE id=?", (movement_id,))

    def list_for_document(self, source_document_type: str, source_document_id: str) -> list[dict]:
        return self._query(
            "SELECT * FROM inventory_ledger WHERE source_document_type=?"
            " AND source_document_id=? ORDER BY occurred_at",
            (source_document_type, source_document_id))

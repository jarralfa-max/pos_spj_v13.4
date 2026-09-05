"""EquipmentAssignmentRepository — persists EquipmentAssignment entities (§19)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.equipment_assignment import EquipmentAssignment
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    dt_str,
    parse_dt,
)


def _to_entity(row: dict) -> EquipmentAssignment:
    return EquipmentAssignment(
        id=row["id"], operation_id=row["operation_id"],
        processing_order_id=row["processing_order_id"], equipment_id=row["equipment_id"],
        assigned_at=parse_dt(row["assigned_at"]), released_at=parse_dt(row["released_at"]))


class EquipmentAssignmentRepository(MeatProcessingRepositoryBase):
    def save(self, assignment: EquipmentAssignment) -> None:
        self._execute(
            "INSERT INTO equipment_assignments (id, operation_id, processing_order_id,"
            " equipment_id, assigned_at, released_at) VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET released_at=excluded.released_at",
            (assignment.id, assignment.operation_id, assignment.processing_order_id,
             assignment.equipment_id, dt_str(assignment.assigned_at),
             dt_str(assignment.released_at)))

    def get(self, assignment_id: str) -> EquipmentAssignment | None:
        row = self._query_one(
            "SELECT * FROM equipment_assignments WHERE id=?", (assignment_id,))
        return None if row is None else _to_entity(row)

    def list_active_by_equipment(self, equipment_id: str) -> list[EquipmentAssignment]:
        rows = self._query(
            "SELECT * FROM equipment_assignments WHERE equipment_id=? AND released_at IS NULL"
            " ORDER BY assigned_at", (equipment_id,))
        return [_to_entity(row) for row in rows]

    def list_by_order(self, processing_order_id: str) -> list[EquipmentAssignment]:
        rows = self._query(
            "SELECT * FROM equipment_assignments WHERE processing_order_id=?"
            " ORDER BY assigned_at", (processing_order_id,))
        return [_to_entity(row) for row in rows]

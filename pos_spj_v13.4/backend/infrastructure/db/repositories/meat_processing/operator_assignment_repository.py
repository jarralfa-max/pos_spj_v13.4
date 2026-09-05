"""OperatorAssignmentRepository — persists OperatorAssignment entities (§32)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.operator_assignment import OperatorAssignment
from backend.domain.meat_processing.enums import OperatorRole
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    dt_str,
    enum_value,
    parse_dt,
)


def _to_entity(row: dict) -> OperatorAssignment:
    return OperatorAssignment(
        id=row["id"], operation_id=row["operation_id"],
        processing_order_id=row["processing_order_id"], user_id=row["user_id"],
        role_type=OperatorRole(row["role_type"]), work_center_id=row["work_center_id"],
        assigned_at=parse_dt(row["assigned_at"]), released_at=parse_dt(row["released_at"]))


class OperatorAssignmentRepository(MeatProcessingRepositoryBase):
    def save(self, assignment: OperatorAssignment) -> None:
        self._execute(
            "INSERT INTO operator_assignments (id, operation_id, processing_order_id,"
            " user_id, role_type, work_center_id, assigned_at, released_at)"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET released_at=excluded.released_at",
            (assignment.id, assignment.operation_id, assignment.processing_order_id,
             assignment.user_id, enum_value(assignment.role_type), assignment.work_center_id,
             dt_str(assignment.assigned_at), dt_str(assignment.released_at)))

    def get(self, assignment_id: str) -> OperatorAssignment | None:
        row = self._query_one(
            "SELECT * FROM operator_assignments WHERE id=?", (assignment_id,))
        return None if row is None else _to_entity(row)

    def list_by_order(self, processing_order_id: str) -> list[OperatorAssignment]:
        rows = self._query(
            "SELECT * FROM operator_assignments WHERE processing_order_id=?"
            " ORDER BY assigned_at", (processing_order_id,))
        return [_to_entity(row) for row in rows]

    def list_active_by_order(self, processing_order_id: str) -> list[OperatorAssignment]:
        rows = self._query(
            "SELECT * FROM operator_assignments WHERE processing_order_id=?"
            " AND released_at IS NULL ORDER BY assigned_at", (processing_order_id,))
        return [_to_entity(row) for row in rows]

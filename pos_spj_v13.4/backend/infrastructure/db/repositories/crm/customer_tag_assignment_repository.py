"""CustomerTagAssignmentRepository — persists CustomerTagAssignment records
(append-only-with-nullable-removed_at — see
backend/domain/crm/entities/customer_tag_assignment.py).
"""

from __future__ import annotations

from backend.domain.crm.entities.customer_tag_assignment import CustomerTagAssignment
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_COLS = (
    "id, customer_id, tag_id, assigned_by_user_id, removed_at, removed_by_user_id,"
    " operation_id, created_at"
)


class CustomerTagAssignmentRepository(CRMRepositoryBase):
    def save(self, assignment: CustomerTagAssignment, *,
             operation_id: str | None = None) -> None:
        self._execute(
            f"INSERT INTO customer_tag_assignments ({_COLS}) VALUES (?,?,?,?,?,?,?,?)",
            self._params(assignment, operation_id or assignment.operation_id))

    def update(self, assignment: CustomerTagAssignment) -> None:
        self._execute(
            "UPDATE customer_tag_assignments SET removed_at=?, removed_by_user_id=?"
            " WHERE id=?",
            (assignment.removed_at, assignment.removed_by_user_id, assignment.id))

    def get(self, assignment_id: str) -> CustomerTagAssignment | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM customer_tag_assignments WHERE id=?", (assignment_id,))
        return self._hydrate(row) if row else None

    def get_active(self, customer_id: str, tag_id: str) -> CustomerTagAssignment | None:
        row = self._query_one(
            f"SELECT {_COLS} FROM customer_tag_assignments"
            " WHERE customer_id=? AND tag_id=? AND removed_at IS NULL"
            " ORDER BY created_at DESC, id DESC LIMIT 1",
            (customer_id, tag_id))
        return self._hydrate(row) if row else None

    def list_active_for_customer(self, customer_id: str) -> list[CustomerTagAssignment]:
        rows = self._query(
            f"SELECT {_COLS} FROM customer_tag_assignments"
            " WHERE customer_id=? AND removed_at IS NULL ORDER BY created_at DESC, id DESC",
            (customer_id,))
        return [self._hydrate(r) for r in rows]

    def list_for_tag(self, tag_id: str) -> list[CustomerTagAssignment]:
        rows = self._query(
            f"SELECT {_COLS} FROM customer_tag_assignments"
            " WHERE tag_id=? ORDER BY created_at DESC, id DESC", (tag_id,))
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _params(assignment: CustomerTagAssignment, operation_id: str | None) -> tuple:
        return (
            assignment.id, assignment.customer_id, assignment.tag_id,
            assignment.assigned_by_user_id, assignment.removed_at,
            assignment.removed_by_user_id, operation_id, assignment.created_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CustomerTagAssignment:
        return CustomerTagAssignment(
            id=row["id"], customer_id=row["customer_id"], tag_id=row["tag_id"],
            assigned_by_user_id=row["assigned_by_user_id"], removed_at=row["removed_at"],
            removed_by_user_id=row["removed_by_user_id"], operation_id=row["operation_id"],
            created_at=row["created_at"],
        )

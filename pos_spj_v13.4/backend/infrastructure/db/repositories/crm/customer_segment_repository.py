"""CustomerSegmentRepository — persists the segment catalog. Mirrors
backend/infrastructure/db/repositories/crm/stage_definition_repository.py.
"""

from __future__ import annotations

from backend.domain.crm.entities.customer_segment import CustomerSegment
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_COLS = "id, code, name, description, rule_definition, active, created_at, updated_at"


class CustomerSegmentRepository(CRMRepositoryBase):
    def save(self, segment: CustomerSegment) -> None:
        self._execute(
            f"INSERT INTO customer_segments ({_COLS}) VALUES (?,?,?,?,?,?,?,?)",
            self._params(segment))

    def update(self, segment: CustomerSegment) -> None:
        self._execute(
            "UPDATE customer_segments SET name=?, description=?, rule_definition=?,"
            " active=?, updated_at=? WHERE id=?",
            (segment.name, segment.description, segment.rule_definition,
             int(segment.active), segment.updated_at, segment.id))

    def get(self, segment_id: str) -> CustomerSegment | None:
        row = self._query_one(f"SELECT {_COLS} FROM customer_segments WHERE id=?",
                              (segment_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> CustomerSegment | None:
        row = self._query_one(f"SELECT {_COLS} FROM customer_segments WHERE code=?",
                              (code.upper(),))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[CustomerSegment]:
        rows = self._query(f"SELECT {_COLS} FROM customer_segments"
                           " WHERE active=1 ORDER BY name ASC")
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _params(segment: CustomerSegment) -> tuple:
        return (segment.id, segment.code, segment.name, segment.description,
                segment.rule_definition, int(segment.active), segment.created_at,
                segment.updated_at)

    @staticmethod
    def _hydrate(row: dict) -> CustomerSegment:
        return CustomerSegment(
            id=row["id"], code=row["code"], name=row["name"],
            description=row["description"] or "",
            rule_definition=row["rule_definition"] or "", active=bool(row["active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

"""CustomerTagRepository — persists the free-form label catalog. Mirrors
backend/infrastructure/db/repositories/crm/stage_definition_repository.py.
"""

from __future__ import annotations

from backend.domain.crm.entities.customer_tag import CustomerTag
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_COLS = "id, code, label, active, created_at, updated_at"


class CustomerTagRepository(CRMRepositoryBase):
    def save(self, tag: CustomerTag) -> None:
        self._execute(f"INSERT INTO customer_tags ({_COLS}) VALUES (?,?,?,?,?,?)",
                      self._params(tag))

    def update(self, tag: CustomerTag) -> None:
        self._execute(
            "UPDATE customer_tags SET label=?, active=?, updated_at=? WHERE id=?",
            (tag.label, int(tag.active), tag.updated_at, tag.id))

    def get(self, tag_id: str) -> CustomerTag | None:
        row = self._query_one(f"SELECT {_COLS} FROM customer_tags WHERE id=?", (tag_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> CustomerTag | None:
        row = self._query_one(f"SELECT {_COLS} FROM customer_tags WHERE code=?",
                              (code.upper(),))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[CustomerTag]:
        rows = self._query(f"SELECT {_COLS} FROM customer_tags WHERE active=1 ORDER BY label ASC")
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _params(tag: CustomerTag) -> tuple:
        return (tag.id, tag.code, tag.label, int(tag.active), tag.created_at, tag.updated_at)

    @staticmethod
    def _hydrate(row: dict) -> CustomerTag:
        return CustomerTag(
            id=row["id"], code=row["code"], label=row["label"], active=bool(row["active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

"""ServiceCaseCategoryRepository — persists the case category catalog."""

from __future__ import annotations

from backend.domain.customer_service.entities.service_case_category import ServiceCaseCategory
from backend.infrastructure.db.repositories.customer_service.base import (
    CustomerServiceRepositoryBase,
)

_CATEGORY_COLS = "id, code, name, active, created_at, updated_at"


class ServiceCaseCategoryRepository(CustomerServiceRepositoryBase):
    def save(self, category: ServiceCaseCategory) -> None:
        self._execute(
            f"INSERT INTO service_case_categories ({_CATEGORY_COLS}) VALUES (?,?,?,?,?,?)",
            (category.id, category.code, category.name, int(category.active),
             category.created_at, category.updated_at))

    def get(self, category_id: str) -> ServiceCaseCategory | None:
        row = self._query_one(
            f"SELECT {_CATEGORY_COLS} FROM service_case_categories WHERE id=?", (category_id,))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[ServiceCaseCategory]:
        rows = self._query(
            f"SELECT {_CATEGORY_COLS} FROM service_case_categories"
            " WHERE active=1 ORDER BY name ASC")
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _hydrate(row: dict) -> ServiceCaseCategory:
        return ServiceCaseCategory(
            id=row["id"], code=row["code"], name=row["name"], active=bool(row["active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

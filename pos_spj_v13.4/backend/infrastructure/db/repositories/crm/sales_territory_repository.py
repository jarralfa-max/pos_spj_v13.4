"""SalesTerritoryRepository — persists the configurable territory catalog.
Mirrors backend/infrastructure/db/repositories/crm/stage_definition_repository.py.
"""

from __future__ import annotations

from backend.domain.crm.entities.sales_territory import SalesTerritory
from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase

_COLS = "id, code, name, description, active, created_at, updated_at"


class SalesTerritoryRepository(CRMRepositoryBase):
    def save(self, territory: SalesTerritory) -> None:
        self._execute(
            f"INSERT INTO sales_territories ({_COLS}) VALUES (?,?,?,?,?,?,?)",
            self._params(territory))

    def update(self, territory: SalesTerritory) -> None:
        self._execute(
            "UPDATE sales_territories SET name=?, description=?, active=?, updated_at=?"
            " WHERE id=?",
            (territory.name, territory.description, int(territory.active),
             territory.updated_at, territory.id))

    def get(self, territory_id: str) -> SalesTerritory | None:
        row = self._query_one(f"SELECT {_COLS} FROM sales_territories WHERE id=?",
                              (territory_id,))
        return self._hydrate(row) if row else None

    def get_by_code(self, code: str) -> SalesTerritory | None:
        row = self._query_one(f"SELECT {_COLS} FROM sales_territories WHERE code=?",
                              (code.upper(),))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[SalesTerritory]:
        rows = self._query(f"SELECT {_COLS} FROM sales_territories"
                           " WHERE active=1 ORDER BY name ASC")
        return [self._hydrate(r) for r in rows]

    @staticmethod
    def _params(territory: SalesTerritory) -> tuple:
        return (territory.id, territory.code, territory.name, territory.description,
                int(territory.active), territory.created_at, territory.updated_at)

    @staticmethod
    def _hydrate(row: dict) -> SalesTerritory:
        return SalesTerritory(
            id=row["id"], code=row["code"], name=row["name"],
            description=row["description"] or "", active=bool(row["active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

"""ProductionAreaRepository — persists ProductionArea entities (§19)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.production_area import ProductionArea
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    bool_int,
    dt_str,
    int_bool,
    parse_dt,
)


def _to_entity(row: dict) -> ProductionArea:
    return ProductionArea(
        id=row["id"], branch_id=row["branch_id"], warehouse_id=row["warehouse_id"],
        code=row["code"], name=row["name"], is_active=int_bool(row["is_active"]),
        created_at=parse_dt(row["created_at"]))


class ProductionAreaRepository(MeatProcessingRepositoryBase):
    def save(self, area: ProductionArea) -> None:
        self._execute(
            "INSERT INTO production_areas (id, branch_id, warehouse_id, code, name,"
            " is_active, created_at) VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET name=excluded.name, is_active=excluded.is_active",
            (area.id, area.branch_id, area.warehouse_id, area.code, area.name,
             bool_int(area.is_active), dt_str(area.created_at)))

    def get(self, area_id: str) -> ProductionArea | None:
        row = self._query_one("SELECT * FROM production_areas WHERE id=?", (area_id,))
        return None if row is None else _to_entity(row)

    def list_by_branch(self, branch_id: str) -> list[ProductionArea]:
        rows = self._query(
            "SELECT * FROM production_areas WHERE branch_id=? ORDER BY code", (branch_id,))
        return [_to_entity(row) for row in rows]

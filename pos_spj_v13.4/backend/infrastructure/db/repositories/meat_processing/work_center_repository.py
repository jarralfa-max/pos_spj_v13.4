"""WorkCenterRepository — persists WorkCenter entities (§19/§33)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.work_center import WorkCenter
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    bool_int,
    dec_str,
    dt_str,
    int_bool,
    parse_dt,
    to_decimal,
)


def _to_entity(row: dict) -> WorkCenter:
    return WorkCenter(
        id=row["id"], production_area_id=row["production_area_id"], code=row["code"],
        name=row["name"], capacity_per_hour=to_decimal(row["capacity_per_hour"]),
        capacity_basis=row["capacity_basis"], is_active=int_bool(row["is_active"]),
        created_at=parse_dt(row["created_at"]))


class WorkCenterRepository(MeatProcessingRepositoryBase):
    def save(self, work_center: WorkCenter) -> None:
        self._execute(
            "INSERT INTO work_centers (id, production_area_id, code, name,"
            " capacity_per_hour, capacity_basis, is_active, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET name=excluded.name,"
            " capacity_per_hour=excluded.capacity_per_hour,"
            " capacity_basis=excluded.capacity_basis, is_active=excluded.is_active",
            (work_center.id, work_center.production_area_id, work_center.code,
             work_center.name, dec_str(work_center.capacity_per_hour),
             work_center.capacity_basis, bool_int(work_center.is_active),
             dt_str(work_center.created_at)))

    def get(self, work_center_id: str) -> WorkCenter | None:
        row = self._query_one("SELECT * FROM work_centers WHERE id=?", (work_center_id,))
        return None if row is None else _to_entity(row)

    def list_by_area(self, production_area_id: str) -> list[WorkCenter]:
        rows = self._query(
            "SELECT * FROM work_centers WHERE production_area_id=? ORDER BY code",
            (production_area_id,))
        return [_to_entity(row) for row in rows]

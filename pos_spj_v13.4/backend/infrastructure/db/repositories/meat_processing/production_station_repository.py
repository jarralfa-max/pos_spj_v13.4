"""ProductionStationRepository — persists ProductionStation entities (§19)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.production_station import ProductionStation
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    bool_int,
    dt_str,
    int_bool,
    parse_dt,
)


def _to_entity(row: dict) -> ProductionStation:
    return ProductionStation(
        id=row["id"], work_center_id=row["work_center_id"], code=row["code"],
        name=row["name"], is_active=int_bool(row["is_active"]),
        created_at=parse_dt(row["created_at"]))


class ProductionStationRepository(MeatProcessingRepositoryBase):
    def save(self, station: ProductionStation) -> None:
        self._execute(
            "INSERT INTO production_stations (id, work_center_id, code, name, is_active,"
            " created_at) VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET name=excluded.name, is_active=excluded.is_active",
            (station.id, station.work_center_id, station.code, station.name,
             bool_int(station.is_active), dt_str(station.created_at)))

    def get(self, station_id: str) -> ProductionStation | None:
        row = self._query_one("SELECT * FROM production_stations WHERE id=?", (station_id,))
        return None if row is None else _to_entity(row)

    def list_by_work_center(self, work_center_id: str) -> list[ProductionStation]:
        rows = self._query(
            "SELECT * FROM production_stations WHERE work_center_id=? ORDER BY code",
            (work_center_id,))
        return [_to_entity(row) for row in rows]

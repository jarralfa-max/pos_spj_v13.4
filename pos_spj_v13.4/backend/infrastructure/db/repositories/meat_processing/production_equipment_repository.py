"""ProductionEquipmentRepository — persists ProductionEquipment entities (§19)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.production_equipment import ProductionEquipment
from backend.domain.meat_processing.enums import EquipmentStatus
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    dt_str,
    enum_value,
    parse_dt,
)


def _to_entity(row: dict) -> ProductionEquipment:
    return ProductionEquipment(
        id=row["id"], work_center_id=row["work_center_id"], station_id=row["station_id"],
        code=row["code"], name=row["name"], equipment_type=row["equipment_type"],
        status=EquipmentStatus(row["status"]),
        last_maintenance_at=parse_dt(row["last_maintenance_at"]),
        created_at=parse_dt(row["created_at"]))


class ProductionEquipmentRepository(MeatProcessingRepositoryBase):
    def save(self, equipment: ProductionEquipment) -> None:
        self._execute(
            "INSERT INTO production_equipment (id, work_center_id, station_id, code, name,"
            " equipment_type, status, last_maintenance_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " last_maintenance_at=excluded.last_maintenance_at",
            (equipment.id, equipment.work_center_id, equipment.station_id, equipment.code,
             equipment.name, equipment.equipment_type, enum_value(equipment.status),
             dt_str(equipment.last_maintenance_at), dt_str(equipment.created_at)))

    def get(self, equipment_id: str) -> ProductionEquipment | None:
        row = self._query_one("SELECT * FROM production_equipment WHERE id=?", (equipment_id,))
        return None if row is None else _to_entity(row)

    def list_by_work_center(self, work_center_id: str) -> list[ProductionEquipment]:
        rows = self._query(
            "SELECT * FROM production_equipment WHERE work_center_id=? ORDER BY code",
            (work_center_id,))
        return [_to_entity(row) for row in rows]

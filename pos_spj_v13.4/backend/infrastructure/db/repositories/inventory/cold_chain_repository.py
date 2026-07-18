"""ColdChainRepository — persists temperature readings and excursions (§21)."""

from __future__ import annotations

from backend.domain.inventory.entities.cold_chain import (
    TemperatureExcursion,
    TemperatureReading,
)
from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    dec_str,
    enum_value,
    now_iso,
)


class ColdChainRepository(InventoryRepositoryBase):
    def save_reading(self, reading: TemperatureReading) -> None:
        self._execute(
            "INSERT INTO inventory_temperature_readings (id, sensor_id, warehouse_id,"
            " location_id, lot_id, temperature, unit, reading_point, status,"
            " captured_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (reading.id, reading.sensor_id, reading.warehouse_id, reading.location_id,
             reading.lot_id, dec_str(reading.temperature), reading.unit,
             enum_value(reading.reading_point), enum_value(reading.status),
             reading.captured_at, now_iso()))

    def save_excursion(self, exc: TemperatureExcursion) -> None:
        self._execute(
            "INSERT INTO inventory_temperature_excursions (id, reading_id, warehouse_id,"
            " lot_id, status, temperature, min_temp, max_temp, action_taken, resolved,"
            " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (exc.id, exc.reading_id, exc.warehouse_id, exc.lot_id,
             enum_value(exc.status), dec_str(exc.temperature), dec_str(exc.min_temp),
             dec_str(exc.max_temp), enum_value(exc.action_taken),
             1 if exc.resolved else 0, exc.created_at))

    def list_readings(self, warehouse_id: str, *, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT * FROM inventory_temperature_readings WHERE warehouse_id=?"
            " ORDER BY captured_at DESC LIMIT ?", (warehouse_id, limit))

    def list_open_excursions(self, *, lot_id: str | None = None) -> list[dict]:
        if lot_id:
            return self._query(
                "SELECT * FROM inventory_temperature_excursions WHERE resolved=0"
                " AND lot_id=? ORDER BY created_at DESC", (lot_id,))
        return self._query(
            "SELECT * FROM inventory_temperature_excursions WHERE resolved=0"
            " ORDER BY created_at DESC")

    def resolve_excursion(self, excursion_id: str) -> None:
        self._execute(
            "UPDATE inventory_temperature_excursions SET resolved=1 WHERE id=?",
            (excursion_id,))

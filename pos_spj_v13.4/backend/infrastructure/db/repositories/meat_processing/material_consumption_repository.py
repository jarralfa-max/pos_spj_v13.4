"""MaterialConsumptionRepository — persists MaterialConsumption entities (§17)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.material_consumption import MaterialConsumption
from backend.domain.meat_processing.enums import ConsumptionStatus
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    dec_str,
    dt_str,
    enum_value,
    parse_dt,
    to_decimal,
)


def _to_entity(row: dict) -> MaterialConsumption:
    return MaterialConsumption(
        id=row["id"], operation_id=row["operation_id"],
        processing_order_id=row["processing_order_id"], product_id=row["product_id"],
        warehouse_id=row["warehouse_id"], captured_by_user_id=row["captured_by_user_id"],
        processing_batch_id=row["processing_batch_id"], lot_id=row["lot_id"],
        location_id=row["location_id"],
        planned_quantity=to_decimal(row["planned_quantity"]),
        planned_weight=to_decimal(row["planned_weight"]),
        actual_quantity=to_decimal(row["actual_quantity"]),
        actual_weight=to_decimal(row["actual_weight"]), unit=row["unit"],
        weighing_id=row["weighing_id"], inventory_operation_id=row["inventory_operation_id"],
        status=ConsumptionStatus(row["status"]), consumed_at=parse_dt(row["consumed_at"]),
        created_at=parse_dt(row["created_at"]))


class MaterialConsumptionRepository(MeatProcessingRepositoryBase):
    def save(self, consumption: MaterialConsumption) -> None:
        self._execute(
            "INSERT INTO material_consumptions (id, operation_id, processing_order_id,"
            " processing_batch_id, product_id, warehouse_id, location_id, lot_id,"
            " captured_by_user_id, planned_quantity, planned_weight, actual_quantity,"
            " actual_weight, unit, weighing_id, inventory_operation_id, status,"
            " consumed_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET lot_id=excluded.lot_id,"
            " location_id=excluded.location_id, actual_quantity=excluded.actual_quantity,"
            " actual_weight=excluded.actual_weight, weighing_id=excluded.weighing_id,"
            " inventory_operation_id=excluded.inventory_operation_id,"
            " status=excluded.status, consumed_at=excluded.consumed_at",
            (consumption.id, consumption.operation_id, consumption.processing_order_id,
             consumption.processing_batch_id, consumption.product_id,
             consumption.warehouse_id, consumption.location_id, consumption.lot_id,
             consumption.captured_by_user_id, dec_str(consumption.planned_quantity),
             dec_str(consumption.planned_weight), dec_str(consumption.actual_quantity),
             dec_str(consumption.actual_weight), consumption.unit, consumption.weighing_id,
             consumption.inventory_operation_id, enum_value(consumption.status),
             dt_str(consumption.consumed_at), dt_str(consumption.created_at)))

    def get(self, consumption_id: str) -> MaterialConsumption | None:
        row = self._query_one(
            "SELECT * FROM material_consumptions WHERE id=?", (consumption_id,))
        return None if row is None else _to_entity(row)

    def list_by_order(self, processing_order_id: str) -> list[MaterialConsumption]:
        rows = self._query(
            "SELECT * FROM material_consumptions WHERE processing_order_id=?"
            " ORDER BY created_at", (processing_order_id,))
        return [_to_entity(row) for row in rows]

    def list_by_batch(self, processing_batch_id: str) -> list[MaterialConsumption]:
        rows = self._query(
            "SELECT * FROM material_consumptions WHERE processing_batch_id=?"
            " ORDER BY created_at", (processing_batch_id,))
        return [_to_entity(row) for row in rows]

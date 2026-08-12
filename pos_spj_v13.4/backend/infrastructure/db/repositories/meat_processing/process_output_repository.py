"""ProcessOutputRepository — persists ProcessOutput entities (§22)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.process_output import ProcessOutput
from backend.domain.meat_processing.enums import OutputQualityStatus, OutputType
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    dec_str,
    dt_str,
    enum_value,
    parse_dt,
    to_decimal,
)


def _to_entity(row: dict) -> ProcessOutput:
    return ProcessOutput(
        id=row["id"], operation_id=row["operation_id"],
        processing_order_id=row["processing_order_id"], product_id=row["product_id"],
        warehouse_id=row["warehouse_id"], captured_by_user_id=row["captured_by_user_id"],
        output_type=OutputType(row["output_type"]),
        processing_batch_id=row["processing_batch_id"], lot_id=row["lot_id"],
        location_id=row["location_id"], quantity=to_decimal(row["quantity"]),
        weight=to_decimal(row["weight"]), pieces=row["pieces"], unit=row["unit"],
        quality_status=OutputQualityStatus(row["quality_status"]),
        inventory_operation_id=row["inventory_operation_id"],
        produced_at=parse_dt(row["produced_at"]))


class ProcessOutputRepository(MeatProcessingRepositoryBase):
    def save(self, output: ProcessOutput) -> None:
        self._execute(
            "INSERT INTO process_outputs (id, operation_id, processing_order_id,"
            " processing_batch_id, product_id, lot_id, warehouse_id, location_id,"
            " captured_by_user_id, output_type, quantity, weight, pieces, unit,"
            " quality_status, inventory_operation_id, produced_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET lot_id=excluded.lot_id,"
            " location_id=excluded.location_id, quality_status=excluded.quality_status,"
            " inventory_operation_id=excluded.inventory_operation_id",
            (output.id, output.operation_id, output.processing_order_id,
             output.processing_batch_id, output.product_id, output.lot_id,
             output.warehouse_id, output.location_id, output.captured_by_user_id,
             enum_value(output.output_type), dec_str(output.quantity),
             dec_str(output.weight), output.pieces, output.unit,
             enum_value(output.quality_status), output.inventory_operation_id,
             dt_str(output.produced_at)))

    def get(self, output_id: str) -> ProcessOutput | None:
        row = self._query_one("SELECT * FROM process_outputs WHERE id=?", (output_id,))
        return None if row is None else _to_entity(row)

    def list_by_order(self, processing_order_id: str) -> list[ProcessOutput]:
        rows = self._query(
            "SELECT * FROM process_outputs WHERE processing_order_id=?"
            " ORDER BY produced_at", (processing_order_id,))
        return [_to_entity(row) for row in rows]

    def list_by_batch(self, processing_batch_id: str) -> list[ProcessOutput]:
        rows = self._query(
            "SELECT * FROM process_outputs WHERE processing_batch_id=?"
            " ORDER BY produced_at", (processing_batch_id,))
        return [_to_entity(row) for row in rows]

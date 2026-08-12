"""ProcessingBatchRepository — persists ProcessingBatch aggregates (§19)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.processing_batch import ProcessingBatch
from backend.domain.meat_processing.enums import ProcessingBatchStatus
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    dec_str,
    dt_str,
    enum_value,
    now_iso,
    parse_dt,
    to_decimal,
)
from backend.shared.ids import new_uuid


def _to_entity(row: dict, source_lot_ids: tuple[str, ...]) -> ProcessingBatch:
    return ProcessingBatch(
        id=row["id"], operation_id=row["operation_id"],
        processing_order_id=row["processing_order_id"], batch_number=row["batch_number"],
        source_lot_ids=source_lot_ids,
        planned_quantity=to_decimal(row["planned_quantity"]),
        planned_weight=to_decimal(row["planned_weight"]),
        actual_quantity=to_decimal(row["actual_quantity"]),
        actual_weight=to_decimal(row["actual_weight"]),
        status=ProcessingBatchStatus(row["status"]), target_lot_code=row["target_lot_code"],
        inventory_lot_id=row["inventory_lot_id"], quality_status=row["quality_status"],
        started_at=parse_dt(row["started_at"]), completed_at=parse_dt(row["completed_at"]),
        created_at=parse_dt(row["created_at"]))


class ProcessingBatchRepository(MeatProcessingRepositoryBase):
    def save(self, batch: ProcessingBatch) -> None:
        self._execute(
            "INSERT INTO processing_batches (id, operation_id, processing_order_id,"
            " batch_number, target_lot_code, inventory_lot_id, quality_status,"
            " planned_quantity, planned_weight, actual_quantity, actual_weight, status,"
            " started_at, completed_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET target_lot_code=excluded.target_lot_code,"
            " inventory_lot_id=excluded.inventory_lot_id,"
            " quality_status=excluded.quality_status,"
            " actual_quantity=excluded.actual_quantity, actual_weight=excluded.actual_weight,"
            " status=excluded.status, started_at=excluded.started_at,"
            " completed_at=excluded.completed_at",
            (batch.id, batch.operation_id, batch.processing_order_id, batch.batch_number,
             batch.target_lot_code, batch.inventory_lot_id, batch.quality_status,
             dec_str(batch.planned_quantity), dec_str(batch.planned_weight),
             dec_str(batch.actual_quantity), dec_str(batch.actual_weight),
             enum_value(batch.status), dt_str(batch.started_at), dt_str(batch.completed_at),
             dt_str(batch.created_at)))
        for lot_id in batch.source_lot_ids:
            self._execute(
                "INSERT INTO processing_batch_source_lots (id, processing_batch_id,"
                " source_lot_id) VALUES (?,?,?) ON CONFLICT(processing_batch_id, source_lot_id)"
                " DO NOTHING",
                (new_uuid(), batch.id, lot_id))

    def _source_lot_ids(self, batch_id: str) -> tuple[str, ...]:
        rows = self._query(
            "SELECT source_lot_id FROM processing_batch_source_lots"
            " WHERE processing_batch_id=? ORDER BY source_lot_id", (batch_id,))
        return tuple(row["source_lot_id"] for row in rows)

    def get(self, batch_id: str) -> ProcessingBatch | None:
        row = self._query_one("SELECT * FROM processing_batches WHERE id=?", (batch_id,))
        if row is None:
            return None
        return _to_entity(row, self._source_lot_ids(batch_id))

    def list_by_order(self, processing_order_id: str) -> list[ProcessingBatch]:
        rows = self._query(
            "SELECT * FROM processing_batches WHERE processing_order_id=?"
            " ORDER BY created_at", (processing_order_id,))
        return [_to_entity(row, self._source_lot_ids(row["id"])) for row in rows]

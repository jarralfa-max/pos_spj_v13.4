"""ProcessWeighingRepository — persists ProcessWeighing entities (§21)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.process_weighing import ProcessWeighing
from backend.domain.meat_processing.enums import WeighingType
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    bool_int,
    dec_str,
    dt_str,
    enum_value,
    int_bool,
    parse_dt,
    to_decimal,
)


def _to_entity(row: dict) -> ProcessWeighing:
    return ProcessWeighing(
        id=row["id"], operation_id=row["operation_id"],
        processing_order_id=row["processing_order_id"],
        captured_by_user_id=row["captured_by_user_id"],
        weighing_type=WeighingType(row["weighing_type"]),
        gross_weight=to_decimal(row["gross_weight"]),
        tare_weight=to_decimal(row["tare_weight"]), unit=row["unit"],
        processing_batch_id=row["processing_batch_id"], scale_id=row["scale_id"],
        stable=int_bool(row["stable"]), manual_override=int_bool(row["manual_override"]),
        authorized_by_user_id=row["authorized_by_user_id"],
        source_reference=row["source_reference"], captured_at=parse_dt(row["captured_at"]))


class ProcessWeighingRepository(MeatProcessingRepositoryBase):
    def save(self, weighing: ProcessWeighing) -> None:
        self._execute(
            "INSERT INTO process_weighings (id, operation_id, processing_order_id,"
            " processing_batch_id, captured_by_user_id, weighing_type, gross_weight,"
            " tare_weight, unit, scale_id, stable, manual_override,"
            " authorized_by_user_id, source_reference, captured_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (weighing.id, weighing.operation_id, weighing.processing_order_id,
             weighing.processing_batch_id, weighing.captured_by_user_id,
             enum_value(weighing.weighing_type), dec_str(weighing.gross_weight),
             dec_str(weighing.tare_weight), weighing.unit, weighing.scale_id,
             bool_int(weighing.stable), bool_int(weighing.manual_override),
             weighing.authorized_by_user_id, weighing.source_reference,
             dt_str(weighing.captured_at)))

    def get(self, weighing_id: str) -> ProcessWeighing | None:
        row = self._query_one("SELECT * FROM process_weighings WHERE id=?", (weighing_id,))
        return None if row is None else _to_entity(row)

    def list_by_order(self, processing_order_id: str) -> list[ProcessWeighing]:
        rows = self._query(
            "SELECT * FROM process_weighings WHERE processing_order_id=?"
            " ORDER BY captured_at", (processing_order_id,))
        return [_to_entity(row) for row in rows]

    def list_by_batch(self, processing_batch_id: str) -> list[ProcessWeighing]:
        rows = self._query(
            "SELECT * FROM process_weighings WHERE processing_batch_id=?"
            " ORDER BY captured_at", (processing_batch_id,))
        return [_to_entity(row) for row in rows]

"""YieldReconciliationRepository — persists YieldReconciliation entities (§26)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.yield_reconciliation import YieldReconciliation
from backend.domain.meat_processing.enums import YieldStatus
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    dec_str,
    dt_str,
    enum_value,
    parse_dt,
    to_decimal,
)


def _to_entity(row: dict) -> YieldReconciliation:
    return YieldReconciliation(
        id=row["id"], operation_id=row["operation_id"],
        processing_order_id=row["processing_order_id"],
        input_quantity=to_decimal(row["input_quantity"]),
        input_weight=to_decimal(row["input_weight"]),
        expected_output_quantity=to_decimal(row["expected_output_quantity"]),
        expected_output_weight=to_decimal(row["expected_output_weight"]),
        actual_output_quantity=to_decimal(row["actual_output_quantity"]),
        actual_output_weight=to_decimal(row["actual_output_weight"]),
        tolerance_pct=to_decimal(row["tolerance_pct"]),
        processing_batch_id=row["processing_batch_id"],
        co_product_weight=to_decimal(row["co_product_weight"]),
        by_product_weight=to_decimal(row["by_product_weight"]),
        waste_weight=to_decimal(row["waste_weight"]), status=YieldStatus(row["status"]),
        reviewed_by_user_id=row["reviewed_by_user_id"],
        calculated_at=parse_dt(row["calculated_at"]))


class YieldReconciliationRepository(MeatProcessingRepositoryBase):
    def save(self, reconciliation: YieldReconciliation) -> None:
        self._execute(
            "INSERT INTO yield_reconciliations (id, operation_id, processing_order_id,"
            " processing_batch_id, input_quantity, input_weight,"
            " expected_output_quantity, expected_output_weight, actual_output_quantity,"
            " actual_output_weight, co_product_weight, by_product_weight, waste_weight,"
            " tolerance_pct, status, reviewed_by_user_id, calculated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " reviewed_by_user_id=excluded.reviewed_by_user_id",
            (reconciliation.id, reconciliation.operation_id,
             reconciliation.processing_order_id, reconciliation.processing_batch_id,
             dec_str(reconciliation.input_quantity), dec_str(reconciliation.input_weight),
             dec_str(reconciliation.expected_output_quantity),
             dec_str(reconciliation.expected_output_weight),
             dec_str(reconciliation.actual_output_quantity),
             dec_str(reconciliation.actual_output_weight),
             dec_str(reconciliation.co_product_weight),
             dec_str(reconciliation.by_product_weight),
             dec_str(reconciliation.waste_weight), dec_str(reconciliation.tolerance_pct),
             enum_value(reconciliation.status), reconciliation.reviewed_by_user_id,
             dt_str(reconciliation.calculated_at)))

    def get(self, reconciliation_id: str) -> YieldReconciliation | None:
        row = self._query_one(
            "SELECT * FROM yield_reconciliations WHERE id=?", (reconciliation_id,))
        return None if row is None else _to_entity(row)

    def list_by_order(self, processing_order_id: str) -> list[YieldReconciliation]:
        rows = self._query(
            "SELECT * FROM yield_reconciliations WHERE processing_order_id=?"
            " ORDER BY calculated_at", (processing_order_id,))
        return [_to_entity(row) for row in rows]

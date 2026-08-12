"""ProcessingOrderRepository — persists ProcessingOrder aggregates (§12/§13)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.processing_order import ProcessingOrder
from backend.domain.meat_processing.enums import ProcessingOrderStatus, ProcessType
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    dec_str,
    dt_str,
    enum_value,
    now_iso,
    parse_dt,
    to_decimal,
)


def _to_entity(row: dict) -> ProcessingOrder:
    return ProcessingOrder(
        id=row["id"], operation_id=row["operation_id"], branch_id=row["branch_id"],
        warehouse_id=row["warehouse_id"], process_type=ProcessType(row["process_type"]),
        target_product_id=row["target_product_id"],
        created_by_user_id=row["created_by_user_id"],
        planned_quantity=to_decimal(row["planned_quantity"]),
        planned_weight=to_decimal(row["planned_weight"]),
        production_area_id=row["production_area_id"], work_center_id=row["work_center_id"],
        recipe_version_id=row["recipe_version_id"],
        cutting_scheme_version_id=row["cutting_scheme_version_id"],
        yield_profile_version_id=row["yield_profile_version_id"],
        source_type=row["source_type"], source_reference_id=row["source_reference_id"],
        scheduled_start_at=parse_dt(row["scheduled_start_at"]),
        scheduled_end_at=parse_dt(row["scheduled_end_at"]),
        priority=row["priority"], status=ProcessingOrderStatus(row["status"]),
        approved_by_user_id=row["approved_by_user_id"],
        released_by_user_id=row["released_by_user_id"],
        started_by_user_id=row["started_by_user_id"],
        completed_by_user_id=row["completed_by_user_id"],
        closed_by_user_id=row["closed_by_user_id"], created_at=parse_dt(row["created_at"]))


class ProcessingOrderRepository(MeatProcessingRepositoryBase):
    def save(self, order: ProcessingOrder) -> None:
        self._execute(
            "INSERT INTO processing_orders (id, operation_id, branch_id, warehouse_id,"
            " production_area_id, work_center_id, process_type, target_product_id,"
            " recipe_version_id, cutting_scheme_version_id, yield_profile_version_id,"
            " source_type, source_reference_id, planned_quantity, planned_weight,"
            " scheduled_start_at, scheduled_end_at, priority, status, created_by_user_id,"
            " approved_by_user_id, released_by_user_id, started_by_user_id,"
            " completed_by_user_id, closed_by_user_id, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " production_area_id=excluded.production_area_id,"
            " work_center_id=excluded.work_center_id,"
            " recipe_version_id=excluded.recipe_version_id,"
            " cutting_scheme_version_id=excluded.cutting_scheme_version_id,"
            " yield_profile_version_id=excluded.yield_profile_version_id,"
            " scheduled_start_at=excluded.scheduled_start_at,"
            " scheduled_end_at=excluded.scheduled_end_at, priority=excluded.priority,"
            " status=excluded.status, approved_by_user_id=excluded.approved_by_user_id,"
            " released_by_user_id=excluded.released_by_user_id,"
            " started_by_user_id=excluded.started_by_user_id,"
            " completed_by_user_id=excluded.completed_by_user_id,"
            " closed_by_user_id=excluded.closed_by_user_id, updated_at=excluded.updated_at",
            (order.id, order.operation_id, order.branch_id, order.warehouse_id,
             order.production_area_id, order.work_center_id, enum_value(order.process_type),
             order.target_product_id, order.recipe_version_id,
             order.cutting_scheme_version_id, order.yield_profile_version_id,
             order.source_type, order.source_reference_id, dec_str(order.planned_quantity),
             dec_str(order.planned_weight), dt_str(order.scheduled_start_at),
             dt_str(order.scheduled_end_at), order.priority, enum_value(order.status),
             order.created_by_user_id, order.approved_by_user_id, order.released_by_user_id,
             order.started_by_user_id, order.completed_by_user_id, order.closed_by_user_id,
             dt_str(order.created_at), now_iso()))

    def get(self, order_id: str) -> ProcessingOrder | None:
        row = self._query_one("SELECT * FROM processing_orders WHERE id=?", (order_id,))
        return None if row is None else _to_entity(row)

    def get_by_operation_id(self, operation_id: str) -> ProcessingOrder | None:
        row = self._query_one(
            "SELECT * FROM processing_orders WHERE operation_id=?", (operation_id,))
        return None if row is None else _to_entity(row)

    def list_by_branch(self, branch_id: str, *, status: ProcessingOrderStatus | None = None
                        ) -> list[ProcessingOrder]:
        if status is None:
            rows = self._query(
                "SELECT * FROM processing_orders WHERE branch_id=? ORDER BY created_at DESC",
                (branch_id,))
        else:
            rows = self._query(
                "SELECT * FROM processing_orders WHERE branch_id=? AND status=?"
                " ORDER BY created_at DESC", (branch_id, enum_value(status)))
        return [_to_entity(row) for row in rows]

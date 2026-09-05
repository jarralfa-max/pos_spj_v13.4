"""ReworkOrderRepository — persists ReworkOrder entities (§29)."""

from __future__ import annotations

from backend.domain.meat_processing.entities.rework_order import ReworkOrder
from backend.domain.meat_processing.enums import ReworkOrigin, ReworkOrderStatus
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    dec_str,
    dt_str,
    enum_value,
    parse_dt,
    to_decimal,
)


def _to_entity(row: dict) -> ReworkOrder:
    return ReworkOrder(
        id=row["id"], operation_id=row["operation_id"],
        source_output_id=row["source_output_id"], product_id=row["product_id"],
        origin=ReworkOrigin(row["origin"]), created_by_user_id=row["created_by_user_id"],
        quantity=to_decimal(row["quantity"]), weight=to_decimal(row["weight"]),
        reason=row["reason"] or "", status=ReworkOrderStatus(row["status"]),
        approved_by_user_id=row["approved_by_user_id"],
        processing_order_id=row["processing_order_id"], created_at=parse_dt(row["created_at"]))


class ReworkOrderRepository(MeatProcessingRepositoryBase):
    def save(self, rework: ReworkOrder) -> None:
        self._execute(
            "INSERT INTO rework_orders (id, operation_id, source_output_id, product_id,"
            " origin, quantity, weight, reason, status, created_by_user_id,"
            " approved_by_user_id, processing_order_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " approved_by_user_id=excluded.approved_by_user_id,"
            " processing_order_id=excluded.processing_order_id",
            (rework.id, rework.operation_id, rework.source_output_id, rework.product_id,
             enum_value(rework.origin), dec_str(rework.quantity), dec_str(rework.weight),
             rework.reason, enum_value(rework.status), rework.created_by_user_id,
             rework.approved_by_user_id, rework.processing_order_id,
             dt_str(rework.created_at)))

    def get(self, rework_id: str) -> ReworkOrder | None:
        row = self._query_one("SELECT * FROM rework_orders WHERE id=?", (rework_id,))
        return None if row is None else _to_entity(row)

    def list_by_source_output(self, source_output_id: str) -> list[ReworkOrder]:
        rows = self._query(
            "SELECT * FROM rework_orders WHERE source_output_id=? ORDER BY created_at",
            (source_output_id,))
        return [_to_entity(row) for row in rows]

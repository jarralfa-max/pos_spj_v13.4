"""RedeliveryRequestRepository (ORD-19). Never commits — the owning
UnitOfWork does.
"""

from __future__ import annotations

from backend.domain.orders_delivery.enums import RedeliveryStatus
from backend.domain.orders_delivery.redelivery import RedeliveryRequest
from backend.infrastructure.db.repositories.orders_delivery.base import (
    OrdersDeliveryRepositoryBase,
    dec_str,
    enum_value,
    to_decimal,
)


class RedeliveryRequestRepository(OrdersDeliveryRepositoryBase):
    def save(self, request: RedeliveryRequest) -> None:
        self._execute(
            """
            INSERT INTO redelivery_requests (
                id, original_delivery_job_id, reason, requested_by_user_id,
                new_window_start, new_window_end, additional_fee, approved_by_user_id,
                status, new_delivery_job_id, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                approved_by_user_id=excluded.approved_by_user_id,
                status=excluded.status,
                new_delivery_job_id=excluded.new_delivery_job_id,
                updated_at=excluded.updated_at
            """,
            (
                request.id, request.original_delivery_job_id, request.reason,
                request.requested_by_user_id, request.new_window_start,
                request.new_window_end, dec_str(request.additional_fee),
                request.approved_by_user_id, enum_value(request.status),
                request.new_delivery_job_id, request.created_at, request.updated_at,
            ),
        )

    def get(self, request_id: str) -> RedeliveryRequest | None:
        row = self._query_one("SELECT * FROM redelivery_requests WHERE id=?", (request_id,))
        return self._hydrate(row) if row else None

    def list_for_job(self, original_delivery_job_id: str) -> list[RedeliveryRequest]:
        rows = self._query(
            "SELECT * FROM redelivery_requests WHERE original_delivery_job_id=?",
            (original_delivery_job_id,))
        return [self._hydrate(row) for row in rows]

    @staticmethod
    def _hydrate(row: dict) -> RedeliveryRequest:
        return RedeliveryRequest(
            id=row["id"], original_delivery_job_id=row["original_delivery_job_id"],
            reason=row["reason"], requested_by_user_id=row["requested_by_user_id"],
            new_window_start=row["new_window_start"], new_window_end=row["new_window_end"],
            additional_fee=to_decimal(row["additional_fee"]),
            approved_by_user_id=row["approved_by_user_id"],
            status=RedeliveryStatus(row["status"]),
            new_delivery_job_id=row["new_delivery_job_id"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

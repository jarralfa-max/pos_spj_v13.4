"""OrdersDeliveryOutboxRepository — persistence for the transactional outbox
(`orders_delivery_outbox`, created in ORD-3). Mirrors
backend/infrastructure/db/repositories/sales/outbox_repository.py, adapted to
this bounded context's richer schema (§57: `aggregate_type`/`aggregate_id`/
`event_type`/`retries`/`last_error`/`next_retry_at`/`processed_at`).

`status` values: PENDING (awaiting/eligible for retry — see `next_retry_at`),
DONE (dispatched), DEAD_LETTER (exhausted `max_attempts`, ORD-24).
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.orders_delivery.base import (
    OrdersDeliveryRepositoryBase,
    now_iso,
)
from backend.shared.ids import new_uuid


class OrdersDeliveryOutboxRepository(OrdersDeliveryRepositoryBase):
    def enqueue(self, *, event_id: str, aggregate_type: str, aggregate_id: str,
                event_type: str, payload_json: str, operation_id: str) -> None:
        self._execute(
            "INSERT INTO orders_delivery_outbox (id, event_id, aggregate_type, aggregate_id,"
            " event_type, payload_json, operation_id, status, created_at)"
            " VALUES (?,?,?,?,?,?,?, 'PENDING', ?)",
            (new_uuid(), event_id, aggregate_type, aggregate_id, event_type,
             payload_json, operation_id, now_iso()))

    def list_pending(self, limit: int = 100) -> list[dict]:
        """ORD-24: a row `mark_failed()` sent back to PENDING with a future
        `next_retry_at` must NOT be picked up again before that time — this
        was a real gap until ORD-24's dispatcher needed genuine retry
        semantics (before that, nothing ever called `mark_failed()`, so the
        gap was dormant)."""
        return self._query(
            "SELECT id, event_id, aggregate_type, aggregate_id, event_type, payload_json,"
            " operation_id, retries, created_at"
            " FROM orders_delivery_outbox WHERE status='PENDING'"
            " AND (next_retry_at IS NULL OR next_retry_at<=?)"
            " ORDER BY created_at LIMIT ?",
            (now_iso(), limit))

    def get_by_event_id(self, event_id: str) -> dict | None:
        return self._query_one(
            "SELECT id, event_id, aggregate_type, aggregate_id, event_type, payload_json,"
            " operation_id, status FROM orders_delivery_outbox WHERE event_id=?", (event_id,))

    def get_by_operation_id(self, operation_id: str) -> dict | None:
        """§58/ORD-22: `operation_id` is globally `UNIQUE` on this table, so
        its presence is a reliable "this exact operation already completed"
        signal — used to make use cases that wrap a non-idempotent external
        call (e.g. Sales' own `RecordSalePaymentUseCase`, which has no
        operation_id dedup of its own) safe to retry without repeating that
        call."""
        return self._query_one(
            "SELECT id, event_id, aggregate_type, aggregate_id, event_type, payload_json,"
            " operation_id, status FROM orders_delivery_outbox WHERE operation_id=?",
            (operation_id,))

    def mark_processed(self, outbox_id: str) -> None:
        self._execute(
            "UPDATE orders_delivery_outbox SET status='DONE', processed_at=? WHERE id=?",
            (now_iso(), outbox_id))

    def mark_failed(self, outbox_id: str, *, error: str, next_retry_at: str | None = None,
                     max_attempts: int = 5) -> None:
        """ORD-24: stays PENDING (with a future `next_retry_at` for
        `list_pending()` to honor) until `retries` reaches `max_attempts`,
        then moves to the terminal `DEAD_LETTER` — mirrors
        `ProcurementOutboxRepository.mark_failed()`'s exact same
        CASE-based promotion, adapted to this table's own column names."""
        self._execute(
            "UPDATE orders_delivery_outbox SET retries=retries+1,"
            " last_error=?, next_retry_at=?,"
            " status=CASE WHEN retries+1>=? THEN 'DEAD_LETTER' ELSE 'PENDING' END"
            " WHERE id=?",
            (error, next_retry_at, max_attempts, outbox_id))

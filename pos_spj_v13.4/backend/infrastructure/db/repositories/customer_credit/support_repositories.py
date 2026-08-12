"""Support repositories: audit log, transactional outbox, processed events.
Mirrors
backend/infrastructure/db/repositories/customer_service/support_repositories.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.infrastructure.db.repositories.customer_credit.base import (
    CustomerCreditRepositoryBase,
)
from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CustomerCreditAuditRepository(CustomerCreditRepositoryBase):
    def record(self, *, action: str, actor_user_id: str | None, customer_id: str | None = None,
               profile_id: str | None = None, authorized_by_user_id: str | None = None,
               before_json: str | None = None, after_json: str | None = None, reason: str = "",
               operation_id: str | None = None) -> None:
        self._execute(
            "INSERT INTO customer_credit_audit_log (id, customer_id, profile_id, action,"
            " actor_user_id, authorized_by_user_id, before_json, after_json, reason,"
            " operation_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), customer_id, profile_id, action, actor_user_id, authorized_by_user_id,
             before_json, after_json, reason, operation_id, _now()))

    def list_for_customer(self, customer_id: str) -> list[dict]:
        return self._query(
            "SELECT action, actor_user_id, authorized_by_user_id, reason, created_at"
            " FROM customer_credit_audit_log WHERE customer_id=? ORDER BY created_at DESC",
            (customer_id,))


class CustomerCreditOutboxRepository(CustomerCreditRepositoryBase):
    def enqueue(self, event_id: str, event_name: str, payload_json: str,
                operation_id: str) -> None:
        self._execute(
            "INSERT INTO customer_credit_outbox (id, event_id, event_name, payload_json,"
            " operation_id, status, created_at) VALUES (?,?,?,?,?, 'PENDING', ?)",
            (new_uuid(), event_id, event_name, payload_json, operation_id, _now()))

    def list_pending(self, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT id, event_id, event_name, payload_json, operation_id, created_at"
            " FROM customer_credit_outbox WHERE status='PENDING' ORDER BY created_at LIMIT ?",
            (limit,))

    def mark_dispatched(self, outbox_id: str) -> None:
        self._execute(
            "UPDATE customer_credit_outbox SET status='DISPATCHED', dispatched_at=? WHERE id=?",
            (_now(), outbox_id))


class CustomerCreditProcessedEventRepository(CustomerCreditRepositoryBase):
    def was_processed(self, event_id: str) -> bool:
        return self._query_one(
            "SELECT event_id FROM customer_credit_processed_events WHERE event_id=?",
            (event_id,)) is not None

    def mark_processed(self, event_id: str, event_name: str, operation_id: str) -> None:
        self._execute(
            "INSERT INTO customer_credit_processed_events (event_id, event_name,"
            " operation_id, processed_at) VALUES (?,?,?,?)",
            (event_id, event_name, operation_id, _now()))

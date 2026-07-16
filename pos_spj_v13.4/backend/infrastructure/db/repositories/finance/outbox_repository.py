"""Outbox repository — transactional outbox for events Finance publishes."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase
from backend.shared.ids import new_uuid


class OutboxRepository(FinanceRepositoryBase):
    def enqueue(self, event_id: str, event_name: str, payload_json: str, operation_id: str) -> None:
        self._execute(
            "INSERT INTO finance_outbox (id, event_id, event_name, payload_json,"
            " operation_id, status, created_at) VALUES (?,?,?,?,?, 'PENDING', ?)",
            (new_uuid(), event_id, event_name, payload_json, operation_id,
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )

    def list_pending(self, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT id, event_id, event_name, payload_json, operation_id, created_at"
            " FROM finance_outbox WHERE status='PENDING' ORDER BY created_at LIMIT ?",
            (limit,),
        )

    def mark_dispatched(self, outbox_id: str) -> None:
        self._execute(
            "UPDATE finance_outbox SET status='DISPATCHED', dispatched_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), outbox_id),
        )

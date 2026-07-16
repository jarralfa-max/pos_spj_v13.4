"""ProcessedEvent repository — idempotency registry for consumed events."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.infrastructure.db.repositories.finance.base import FinanceRepositoryBase


class ProcessedEventRepository(FinanceRepositoryBase):
    def was_processed(self, event_id: str) -> bool:
        row = self._query_one(
            "SELECT event_id FROM finance_processed_events WHERE event_id=?", (event_id,)
        )
        return row is not None

    def mark_processed(self, event_id: str, event_name: str, operation_id: str) -> None:
        self._execute(
            "INSERT INTO finance_processed_events (event_id, event_name, operation_id, processed_at)"
            " VALUES (?,?,?,?)",
            (event_id, event_name, operation_id,
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )

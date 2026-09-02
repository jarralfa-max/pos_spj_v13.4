"""CommercialInstrumentsOutboxRepository — mirrors
backend/infrastructure/db/repositories/loyalty/outbox_repository.py exactly.
No dispatcher wired yet — same confirmed gap as every other bounded
context's own outbox in this repo."""

from __future__ import annotations

from backend.infrastructure.db.repositories.commercial_instruments.base import (
    CommercialInstrumentsRepositoryBase,
    now_iso,
)
from backend.shared.ids import new_uuid


class CommercialInstrumentsOutboxRepository(CommercialInstrumentsRepositoryBase):
    def enqueue(self, *, event_id: str, event_name: str, payload_json: str,
                operation_id: str) -> None:
        self._execute(
            "INSERT INTO commercial_instruments_outbox (id, event_id, event_name,"
            " payload_json, operation_id, status, created_at) VALUES (?,?,?,?,?, 'PENDING', ?)",
            (new_uuid(), event_id, event_name, payload_json, operation_id, now_iso()))

    def list_pending(self, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT id, event_id, event_name, payload_json, operation_id, created_at"
            " FROM commercial_instruments_outbox WHERE status='PENDING'"
            " ORDER BY created_at LIMIT ?", (limit,))

    def mark_dispatched(self, outbox_id: str) -> None:
        self._execute(
            "UPDATE commercial_instruments_outbox SET status='DISPATCHED', dispatched_at=?"
            " WHERE id=?", (now_iso(), outbox_id))

"""Offline-first sync repositories (§57, INV-22).

``SyncDispatchRepository`` tracks the per-node dispatch state of each outbox event
(monotonic sequence + retry/backoff + dead-letter). ``SyncCursorRepository`` tracks
how far each node/stream has been confirmed synced. Sequence and attempt counters
are INTEGER (ordering/counters, never money) — Decimal rule does not apply.
"""

from __future__ import annotations

from backend.infrastructure.db.repositories.inventory.base import (
    InventoryRepositoryBase,
    now_iso,
)
from backend.shared.ids import new_uuid


class SyncDispatchRepository(InventoryRepositoryBase):
    def next_sequence(self, node_id: str) -> int:
        return int(self._scalar(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM inventory_sync_dispatch"
            " WHERE node_id=?", (node_id,), default=1))

    def exists_for_event(self, event_id: str) -> bool:
        return self._query_one(
            "SELECT id FROM inventory_sync_dispatch WHERE event_id=?", (event_id,)) is not None

    def create(self, *, event_id: str, operation_id: str, node_id: str, sequence: int,
               max_attempts: int = 5, next_attempt_at: str | None = None) -> str:
        row_id = new_uuid()
        self._execute(
            "INSERT INTO inventory_sync_dispatch (id, event_id, operation_id, node_id,"
            " sequence, status, attempts, max_attempts, next_attempt_at, created_at)"
            " VALUES (?,?,?,?,?, 'PENDING', 0, ?, ?, ?)",
            (row_id, event_id, operation_id, node_id, sequence, max_attempts,
             next_attempt_at, now_iso()))
        return row_id

    def list_due(self, node_id: str, *, now: str, limit: int = 100) -> list[dict]:
        """PENDING rows whose backoff has elapsed, oldest sequence first."""
        return self._query(
            "SELECT * FROM inventory_sync_dispatch WHERE node_id=? AND status='PENDING'"
            " AND (next_attempt_at IS NULL OR next_attempt_at<=?)"
            " ORDER BY sequence LIMIT ?", (node_id, now, limit))

    def mark_dispatched(self, dispatch_id: str, *, attempts: int) -> None:
        self._execute(
            "UPDATE inventory_sync_dispatch SET status='DISPATCHED', attempts=?,"
            " last_error=NULL, next_attempt_at=NULL, dispatched_at=? WHERE id=?",
            (attempts, now_iso(), dispatch_id))

    def schedule_retry(self, dispatch_id: str, *, attempts: int, next_attempt_at: str,
                       last_error: str) -> None:
        self._execute(
            "UPDATE inventory_sync_dispatch SET attempts=?, next_attempt_at=?,"
            " last_error=? WHERE id=?",
            (attempts, next_attempt_at, last_error[:500], dispatch_id))

    def dead_letter(self, dispatch_id: str, *, attempts: int, last_error: str) -> None:
        self._execute(
            "UPDATE inventory_sync_dispatch SET status='DEAD_LETTER', attempts=?,"
            " last_error=?, next_attempt_at=NULL WHERE id=?",
            (attempts, last_error[:500], dispatch_id))

    def list_by_status(self, node_id: str, status: str) -> list[dict]:
        return self._query(
            "SELECT * FROM inventory_sync_dispatch WHERE node_id=? AND status=?"
            " ORDER BY sequence", (node_id, status))

    def synced_high_water(self, node_id: str) -> int:
        """Highest sequence with no still-PENDING dispatch at or below it: the last
        contiguously-synced point (dispatched or dead-lettered all clear it)."""
        lowest_pending = self._scalar(
            "SELECT MIN(sequence) FROM inventory_sync_dispatch WHERE node_id=?"
            " AND status='PENDING'", (node_id,))
        if lowest_pending is not None:
            return int(lowest_pending) - 1
        return int(self._scalar(
            "SELECT MAX(sequence) FROM inventory_sync_dispatch WHERE node_id=?",
            (node_id,), default=0))


class SyncCursorRepository(InventoryRepositoryBase):
    def get(self, node_id: str, stream: str = "outbox") -> dict | None:
        return self._query_one(
            "SELECT node_id, stream, last_sequence FROM inventory_sync_cursor"
            " WHERE node_id=? AND stream=?", (node_id, stream))

    def advance(self, node_id: str, sequence: int, stream: str = "outbox") -> None:
        """Move the cursor forward to ``sequence`` (never backward)."""
        self._execute(
            "INSERT INTO inventory_sync_cursor (id, node_id, stream, last_sequence,"
            " updated_at) VALUES (?,?,?,?,?)"
            " ON CONFLICT(node_id, stream) DO UPDATE SET"
            " last_sequence=MAX(inventory_sync_cursor.last_sequence, excluded.last_sequence),"
            " updated_at=excluded.updated_at",
            (new_uuid(), node_id, stream, sequence, now_iso()))

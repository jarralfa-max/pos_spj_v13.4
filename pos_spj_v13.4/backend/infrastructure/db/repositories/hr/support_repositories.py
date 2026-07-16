"""Support repositories: audit log, processed events, transactional outbox."""

from __future__ import annotations

from datetime import datetime, timezone

from backend.infrastructure.db.repositories.hr.base import HRRepositoryBase
from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class HRAuditRepository(HRRepositoryBase):
    def record(self, *, action: str, actor_user_id: str | None, entity_type: str,
               entity_id: str | None, detail: str, operation_id: str | None = None) -> None:
        self._execute(
            "INSERT INTO hr_audit_log (id, action, actor_user_id, entity_type,"
            " entity_id, detail, operation_id, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (new_uuid(), action, actor_user_id, entity_type, entity_id, detail,
             operation_id, _now()))

    def list_for_entity(self, entity_type: str, entity_id: str) -> list[dict]:
        return self._query(
            "SELECT action, actor_user_id, detail, created_at FROM hr_audit_log"
            " WHERE entity_type=? AND entity_id=? ORDER BY created_at DESC",
            (entity_type, entity_id))


class HRProcessedEventRepository(HRRepositoryBase):
    def was_processed(self, event_id: str) -> bool:
        return self._query_one(
            "SELECT event_id FROM hr_processed_events WHERE event_id=?", (event_id,)) is not None

    def mark_processed(self, event_id: str, event_name: str, operation_id: str) -> None:
        self._execute(
            "INSERT INTO hr_processed_events (event_id, event_name, operation_id, processed_at)"
            " VALUES (?,?,?,?)", (event_id, event_name, operation_id, _now()))


class HROutboxRepository(HRRepositoryBase):
    def enqueue(self, event_id: str, event_name: str, payload_json: str, operation_id: str) -> None:
        self._execute(
            "INSERT INTO hr_outbox (id, event_id, event_name, payload_json, operation_id,"
            " status, created_at) VALUES (?,?,?,?,?, 'PENDING', ?)",
            (new_uuid(), event_id, event_name, payload_json, operation_id, _now()))

    def list_pending(self, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT id, event_id, event_name, payload_json, operation_id, created_at"
            " FROM hr_outbox WHERE status='PENDING' ORDER BY created_at LIMIT ?", (limit,))

    def mark_dispatched(self, outbox_id: str) -> None:
        self._execute(
            "UPDATE hr_outbox SET status='DISPATCHED', dispatched_at=? WHERE id=?",
            (_now(), outbox_id))

"""Support repositories: audit log, transactional outbox, processed events.
Mirrors backend/infrastructure/db/repositories/customers/support_repositories.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.infrastructure.db.repositories.crm.base import CRMRepositoryBase
from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CRMAuditRepository(CRMRepositoryBase):
    def record(self, *, action: str, actor_user_id: str | None, lead_id: str | None = None,
               opportunity_id: str | None = None, activity_id: str | None = None,
               task_id: str | None = None, note_id: str | None = None,
               before_json: str | None = None, after_json: str | None = None, reason: str = "",
               operation_id: str | None = None) -> None:
        self._execute(
            "INSERT INTO crm_audit_log (id, lead_id, opportunity_id, activity_id, task_id,"
            " note_id, action, actor_user_id, before_json, after_json, reason, operation_id,"
            " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), lead_id, opportunity_id, activity_id, task_id, note_id, action,
             actor_user_id, before_json, after_json, reason, operation_id, _now()))

    def list_for_lead(self, lead_id: str) -> list[dict]:
        return self._query(
            "SELECT action, actor_user_id, reason, created_at FROM crm_audit_log"
            " WHERE lead_id=? ORDER BY created_at DESC", (lead_id,))

    def list_for_opportunity(self, opportunity_id: str) -> list[dict]:
        return self._query(
            "SELECT action, actor_user_id, reason, created_at FROM crm_audit_log"
            " WHERE opportunity_id=? ORDER BY created_at DESC", (opportunity_id,))

    def list_for_activity(self, activity_id: str) -> list[dict]:
        return self._query(
            "SELECT action, actor_user_id, reason, created_at FROM crm_audit_log"
            " WHERE activity_id=? ORDER BY created_at DESC", (activity_id,))

    def list_for_task(self, task_id: str) -> list[dict]:
        return self._query(
            "SELECT action, actor_user_id, reason, created_at FROM crm_audit_log"
            " WHERE task_id=? ORDER BY created_at DESC", (task_id,))


class CRMOutboxRepository(CRMRepositoryBase):
    def enqueue(self, event_id: str, event_name: str, payload_json: str,
                operation_id: str) -> None:
        self._execute(
            "INSERT INTO crm_outbox (id, event_id, event_name, payload_json,"
            " operation_id, status, created_at) VALUES (?,?,?,?,?, 'PENDING', ?)",
            (new_uuid(), event_id, event_name, payload_json, operation_id, _now()))

    def list_pending(self, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT id, event_id, event_name, payload_json, operation_id, created_at"
            " FROM crm_outbox WHERE status='PENDING' ORDER BY created_at LIMIT ?", (limit,))

    def mark_dispatched(self, outbox_id: str) -> None:
        self._execute(
            "UPDATE crm_outbox SET status='DISPATCHED', dispatched_at=? WHERE id=?",
            (_now(), outbox_id))


class CRMProcessedEventRepository(CRMRepositoryBase):
    def was_processed(self, event_id: str) -> bool:
        return self._query_one(
            "SELECT event_id FROM crm_processed_events WHERE event_id=?",
            (event_id,)) is not None

    def mark_processed(self, event_id: str, event_name: str, operation_id: str) -> None:
        self._execute(
            "INSERT INTO crm_processed_events (event_id, event_name, operation_id,"
            " processed_at) VALUES (?,?,?,?)", (event_id, event_name, operation_id, _now()))

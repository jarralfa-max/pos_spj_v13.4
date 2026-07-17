"""Support repositories: audit log, transactional outbox, processed events.

Bank-sensitive fields must never be written raw into audit/outbox payloads —
callers mask them (e.g. masked CLABE) before recording.
"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.infrastructure.db.repositories.suppliers.base import SupplierRepositoryBase
from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SupplierAuditRepository(SupplierRepositoryBase):
    def record(self, *, action: str, actor_user_id: str | None, supplier_id: str | None,
               before_json: str | None = None, after_json: str | None = None,
               reason: str = "", operation_id: str | None = None) -> None:
        self._execute(
            "INSERT INTO supplier_audit_log (id, supplier_id, action, actor_user_id,"
            " before_json, after_json, reason, operation_id, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (new_uuid(), supplier_id, action, actor_user_id, before_json, after_json,
             reason, operation_id, _now()))

    def list_for_supplier(self, supplier_id: str) -> list[dict]:
        return self._query(
            "SELECT action, actor_user_id, reason, created_at FROM supplier_audit_log"
            " WHERE supplier_id=? ORDER BY created_at DESC", (supplier_id,))


class SupplierOutboxRepository(SupplierRepositoryBase):
    def enqueue(self, event_id: str, event_name: str, payload_json: str,
                operation_id: str) -> None:
        self._execute(
            "INSERT INTO supplier_outbox (id, event_id, event_name, payload_json,"
            " operation_id, status, created_at) VALUES (?,?,?,?,?, 'PENDING', ?)",
            (new_uuid(), event_id, event_name, payload_json, operation_id, _now()))

    def list_pending(self, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT id, event_id, event_name, payload_json, operation_id, created_at"
            " FROM supplier_outbox WHERE status='PENDING' ORDER BY created_at LIMIT ?", (limit,))

    def mark_dispatched(self, outbox_id: str) -> None:
        self._execute(
            "UPDATE supplier_outbox SET status='DISPATCHED', dispatched_at=? WHERE id=?",
            (_now(), outbox_id))


class SupplierProcessedEventRepository(SupplierRepositoryBase):
    def was_processed(self, event_id: str) -> bool:
        return self._query_one(
            "SELECT event_id FROM supplier_processed_events WHERE event_id=?",
            (event_id,)) is not None

    def mark_processed(self, event_id: str, event_name: str, operation_id: str) -> None:
        self._execute(
            "INSERT INTO supplier_processed_events (event_id, event_name, operation_id,"
            " processed_at) VALUES (?,?,?,?)", (event_id, event_name, operation_id, _now()))

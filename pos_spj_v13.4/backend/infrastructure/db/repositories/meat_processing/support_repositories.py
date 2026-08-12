"""Support repositories: hot-authorization log, audit log, transactional outbox,
and processed-events registry. Mirrors
backend/infrastructure/db/repositories/inventory/support_repositories.py.

Sensitive fields must never be written raw into audit/outbox payloads — callers
mask them first.
"""

from __future__ import annotations

from backend.domain.meat_processing.value_objects.authorization_grant import (
    AuthorizationGrant,
)
from backend.infrastructure.db.repositories.meat_processing.base import (
    MeatProcessingRepositoryBase,
    now_iso,
    opt_dec_str,
)
from backend.shared.ids import new_uuid


class MeatProcessingAuthorizationLogRepository(MeatProcessingRepositoryBase):
    """Immutable log of hot authorizations (§52): who authorized which exception."""

    def record(self, grant: AuthorizationGrant) -> str:
        row_id = new_uuid()
        self._execute(
            "INSERT INTO meat_processing_authorization_log (id, permission_code,"
            " requested_by, authorized_by, operation_id, reason, quantity, weight,"
            " value_reference, device_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (row_id, grant.permission_code, grant.requested_by, grant.authorized_by,
             grant.operation_id, grant.reason, opt_dec_str(grant.quantity),
             opt_dec_str(grant.weight), opt_dec_str(grant.value_reference),
             grant.device_id, now_iso()))
        return row_id


class MeatProcessingAuditRepository(MeatProcessingRepositoryBase):
    def record(self, *, entity_type: str, entity_id: str, action: str,
               user_id: str | None = None, authorized_by: str | None = None,
               operation_id: str | None = None, before_json: str | None = None,
               after_json: str | None = None, reason: str | None = None,
               branch_id: str | None = None, warehouse_id: str | None = None,
               processing_order_id: str | None = None,
               processing_batch_id: str | None = None, device_id: str | None = None,
               source_module: str = "meat_processing") -> None:
        self._execute(
            "INSERT INTO meat_processing_audit_log (id, entity_type, entity_id, action,"
            " user_id, authorized_by, operation_id, before_json, after_json, reason,"
            " branch_id, warehouse_id, processing_order_id, processing_batch_id,"
            " device_id, source_module, occurred_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), entity_type, entity_id, action, user_id, authorized_by,
             operation_id, before_json, after_json, reason or "", branch_id, warehouse_id,
             processing_order_id, processing_batch_id, device_id, source_module, now_iso()))

    def list_for_entity(self, entity_type: str, entity_id: str) -> list[dict]:
        return self._query(
            "SELECT action, user_id, authorized_by, reason, occurred_at"
            " FROM meat_processing_audit_log WHERE entity_type=? AND entity_id=?"
            " ORDER BY occurred_at", (entity_type, entity_id))


class MeatProcessingOutboxRepository(MeatProcessingRepositoryBase):
    """Transactional outbox: events are enqueued in the same transaction as the
    state change, then published post-commit."""

    def enqueue(self, *, event_id: str, event_name: str, payload_json: str,
                operation_id: str) -> None:
        self._execute(
            "INSERT INTO meat_processing_outbox (id, event_id, event_name, payload_json,"
            " operation_id, status, created_at) VALUES (?,?,?,?,?, 'PENDING', ?)",
            (new_uuid(), event_id, event_name, payload_json, operation_id, now_iso()))

    def list_pending(self, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT id, event_id, event_name, payload_json, operation_id, created_at"
            " FROM meat_processing_outbox WHERE status='PENDING' ORDER BY created_at LIMIT ?",
            (limit,))

    def get_by_event_id(self, event_id: str) -> dict | None:
        return self._query_one(
            "SELECT id, event_id, event_name, payload_json, operation_id, status"
            " FROM meat_processing_outbox WHERE event_id=?", (event_id,))

    def mark_dispatched(self, outbox_id: str) -> None:
        self._execute(
            "UPDATE meat_processing_outbox SET status='DISPATCHED', dispatched_at=?"
            " WHERE id=?", (now_iso(), outbox_id))


class MeatProcessingProcessedEventRepository(MeatProcessingRepositoryBase):
    def was_processed(self, event_id: str) -> bool:
        return self._query_one(
            "SELECT event_id FROM meat_processing_processed_events WHERE event_id=?",
            (event_id,)) is not None

    def mark_processed(self, event_id: str, event_name: str, operation_id: str) -> None:
        self._execute(
            "INSERT INTO meat_processing_processed_events (event_id, event_name,"
            " operation_id, processed_at) VALUES (?,?,?,?)",
            (event_id, event_name, operation_id, now_iso()))

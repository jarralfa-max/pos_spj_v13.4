"""Support repositories: authorization log, audit log, transactional outbox,
processed-events registry, and document-number sequencing.

Sensitive fields (bank/CLABE/PIN/tokens) must never be written raw into audit or
outbox payloads — callers mask them before recording.
"""

from __future__ import annotations

from decimal import Decimal

from backend.domain.procurement.value_objects import DocumentNumber
from backend.infrastructure.db.repositories.procurement.base import (
    ProcurementRepositoryBase,
    dec_str,
    now_iso,
)
from backend.shared.ids import new_uuid


class PurchaseAuthorizationLogRepository(ProcurementRepositoryBase):
    """Immutable log of hot authorizations (§64): who authorized which exception."""

    def record(self, *, operation_id: str, permission_code: str, requested_by_user_id: str,
               authorized_by_user_id: str, reason: str, amount: Decimal,
               document_id: str | None = None, terminal_id: str | None = None) -> str:
        row_id = new_uuid()
        self._execute(
            "INSERT INTO purchase_authorization_log (id, operation_id, permission_code,"
            " requested_by_user_id, authorized_by_user_id, reason, amount, document_id,"
            " terminal_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (row_id, operation_id, permission_code, requested_by_user_id,
             authorized_by_user_id, reason, dec_str(amount), document_id, terminal_id,
             now_iso()))
        return row_id


class ProcurementAuditRepository(ProcurementRepositoryBase):
    def record(self, *, action: str, actor_user_id: str | None, document_id: str | None = None,
               authorized_by: str | None = None, before_json: str | None = None,
               after_json: str | None = None, reason: str = "",
               operation_id: str | None = None, branch_id: str | None = None,
               terminal_id: str | None = None, source_channel: str | None = None) -> None:
        self._execute(
            "INSERT INTO procurement_audit_log (id, document_id, action, actor_user_id,"
            " authorized_by, before_json, after_json, reason, operation_id, branch_id,"
            " terminal_id, source_channel, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), document_id, action, actor_user_id, authorized_by, before_json,
             after_json, reason, operation_id, branch_id, terminal_id, source_channel,
             now_iso()))

    def list_for_document(self, document_id: str) -> list[dict]:
        return self._query(
            "SELECT action, actor_user_id, authorized_by, reason, created_at"
            " FROM procurement_audit_log WHERE document_id=? ORDER BY created_at",
            (document_id,))


class ProcurementOutboxRepository(ProcurementRepositoryBase):
    """Transactional outbox: events are enqueued in the same transaction as the
    state change, then published post-commit."""

    def enqueue(self, *, event_id: str, event_name: str, payload_json: str,
                operation_id: str) -> None:
        self._execute(
            "INSERT INTO procurement_outbox (id, event_id, event_name, payload_json,"
            " operation_id, status, created_at) VALUES (?,?,?,?,?, 'PENDING', ?)",
            (new_uuid(), event_id, event_name, payload_json, operation_id, now_iso()))

    def list_pending(self, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT id, event_id, event_name, payload_json, operation_id, created_at"
            " FROM procurement_outbox WHERE status='PENDING' ORDER BY created_at LIMIT ?",
            (limit,))

    def mark_dispatched(self, outbox_id: str) -> None:
        self._execute(
            "UPDATE procurement_outbox SET status='DISPATCHED', dispatched_at=? WHERE id=?",
            (now_iso(), outbox_id))


class ProcurementProcessedEventRepository(ProcurementRepositoryBase):
    def was_processed(self, event_id: str) -> bool:
        return self._query_one(
            "SELECT event_id FROM procurement_processed_events WHERE event_id=?",
            (event_id,)) is not None

    def mark_processed(self, event_id: str, event_name: str, operation_id: str) -> None:
        self._execute(
            "INSERT INTO procurement_processed_events (event_id, event_name, operation_id,"
            " processed_at) VALUES (?,?,?,?)",
            (event_id, event_name, operation_id, now_iso()))


class DocumentSequenceRepository(ProcurementRepositoryBase):
    """Allocates the next per-type, per-year document sequence from existing rows.

    The human code (PREFIX-YYYY-NNNNNN) never replaces the UUID; it is a readable
    reference. UNIQUE(document_number) guarantees no collision even under races.
    """

    _TABLE_BY_PREFIX = {
        "CD": "direct_purchases",
        "SC": "purchase_requisitions",
        "RFQ": "requests_for_quotation",
        "OC": "purchase_orders",
        "REC": "goods_receipts",
        "FPR": "supplier_invoices",
    }

    def next_number(self, prefix: str, year: int) -> DocumentNumber:
        table = self._TABLE_BY_PREFIX.get(prefix)
        if table is None:
            return DocumentNumber(prefix, year, 1)
        like = f"{prefix}-{year:04d}-%"
        highest = self._scalar(
            f"SELECT MAX(document_number) FROM {table} WHERE document_number LIKE ?",
            (like,))
        sequence = 1 if not highest else int(str(highest).split("-")[-1]) + 1
        return DocumentNumber(prefix, year, sequence)

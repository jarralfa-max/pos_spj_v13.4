"""Support repositories: authorization log, audit log, transactional outbox,
processed-events registry, and document-number sequencing.

Sensitive fields (bank/CLABE/PIN/tokens) must never be written raw into audit or
outbox payloads — callers mask them before recording.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from backend.domain.document_output.entities.document_number_sequence import DocumentNumberSequence
from backend.domain.document_output.enums import SequenceResetPolicy
from backend.domain.procurement.value_objects import DocumentNumber
from backend.infrastructure.db.repositories.document_output.document_number_sequence_repository import (
    SqliteDocumentNumberSequenceRepository,
)
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
                operation_id: str, deduplication_key: str | None = None) -> None:
        self._execute(
            "INSERT INTO procurement_outbox (id, event_id, event_name, payload_json,"
            " operation_id, deduplication_key, status, created_at)"
            " VALUES (?,?,?,?,?,?, 'PENDING', ?)",
            (new_uuid(), event_id, event_name, payload_json, operation_id,
             deduplication_key, now_iso()))

    def list_pending(self, limit: int = 100) -> list[dict]:
        return self._query(
            "SELECT id, event_id, event_name, payload_json, operation_id,"
            " attempt_count, created_at"
            " FROM procurement_outbox WHERE status='PENDING'"
            " AND (next_attempt_at IS NULL OR next_attempt_at<=?)"
            " ORDER BY created_at LIMIT ?",
            (now_iso(), limit))

    def mark_dispatched(self, outbox_id: str) -> None:
        self._execute(
            "UPDATE procurement_outbox SET status='DISPATCHED', dispatched_at=? WHERE id=?",
            (now_iso(), outbox_id))

    def mark_failed(self, outbox_id: str, error: str, *, max_attempts: int,
                    next_attempt_at: str) -> None:
        self._execute(
            "UPDATE procurement_outbox SET attempt_count=attempt_count+1,"
            " last_error=?, next_attempt_at=?,"
            " status=CASE WHEN attempt_count+1>=? THEN 'DEAD_LETTER' ELSE 'PENDING' END"
            " WHERE id=?",
            (error[:1000], next_attempt_at, max_attempts, outbox_id))


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
    """Allocates the next per-type, per-year document sequence.

    The human code (PREFIX-YYYY-NNNNNN) never replaces the UUID; it is a
    readable reference. SET-16 cutover (2026-08-23): the counter now lives
    in `document_number_sequences` (SET-16), advanced by a single atomic
    `UPDATE ... RETURNING` (`SqliteDocumentNumberSequenceRepository.
    reserve_and_get()`) — not the original `SELECT MAX(document_number)+1`
    Python read-modify-write this method used to do, which relied entirely
    on `UNIQUE(document_number)` catching a race after the fact (a raw
    `sqlite3.IntegrityError` on whichever concurrent caller lost). On first
    use of a prefix, the sequence is bootstrapped from that exact same
    `MAX(document_number)` scan (still below, now only for bootstrapping)
    so numbering continues seamlessly — never collides with numbers
    already issued by the pre-cutover legacy path. Signature and return
    type are unchanged: no caller of `next_number()` needed to change.

    One behavioral difference from the old scan, accepted deliberately:
    there is ONE persisted sequence row per prefix (not per prefix+year),
    so `year` is expected to only advance forward across calls within a
    row's lifetime — exactly what `_year()` (`date.today().year`) always
    gives in real use. The old scan re-read the live table fresh every
    call, so it happened to tolerate an out-of-order `year` argument; the
    new counter does not, since that is not a real scenario any real
    caller produces.
    """

    _TABLE_BY_PREFIX = {
        "CD": "direct_purchases",
        "SC": "purchase_requisitions",
        "RFQ": "requests_for_quotation",
        "OC": "purchase_orders",
        "REC": "goods_receipts",
        "FPR": "supplier_invoices",
        "DEV": "purchase_returns",
    }

    def next_number(self, prefix: str, year: int) -> DocumentNumber:
        if prefix not in self._TABLE_BY_PREFIX:
            return DocumentNumber(prefix, year, 1)

        seq_repo = SqliteDocumentNumberSequenceRepository(self._conn)
        period_key = f"{year:04d}"
        sequence = seq_repo.get_by_prefix(prefix) or self._bootstrap_sequence(
            seq_repo, prefix=prefix, period_key=period_key)
        value = seq_repo.reserve_and_get(sequence.id, period_key=period_key)
        return DocumentNumber(prefix, year, value)

    def _bootstrap_sequence(
        self, seq_repo: SqliteDocumentNumberSequenceRepository, *, prefix: str, period_key: str,
    ) -> DocumentNumberSequence:
        """First-ever use of `prefix` post-cutover: seed the new counter
        from the legacy MAX(document_number) scan so it continues exactly
        where the old path left off. A concurrent double-bootstrap is safe
        — `document_number_sequences.prefix` is UNIQUE, so the losing
        INSERT fails cleanly and that caller just re-fetches the winner's
        row instead of raising."""
        table = self._TABLE_BY_PREFIX[prefix]
        like = f"{prefix}-{period_key}-%"
        highest = self._scalar(
            f"SELECT MAX(document_number) FROM {table} WHERE document_number LIKE ?", (like,))
        starting_value = 0 if not highest else int(str(highest).split("-")[-1])

        sequence = DocumentNumberSequence.create(prefix=prefix, reset_policy=SequenceResetPolicy.YEARLY)
        sequence.period_key = period_key
        sequence.current_value = starting_value
        try:
            seq_repo.save(sequence)
        except sqlite3.IntegrityError:
            existing = seq_repo.get_by_prefix(prefix)
            if existing is None:
                raise
            return existing
        return sequence

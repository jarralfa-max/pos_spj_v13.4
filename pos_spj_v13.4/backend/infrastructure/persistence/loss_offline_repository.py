"""SQLite persistence adapter for LOSS-22; schema remains migration-owned."""

from __future__ import annotations

from datetime import datetime, timezone
import json

from backend.application.losses.offline import (
    LossSyncEnvelope,
    OfflineLossDraft,
    StagedLossEvidence,
)
from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SQLiteLossOfflineRepository:
    def __init__(self, connection) -> None:
        self._db = connection

    def save_draft(self, draft: OfflineLossDraft,
                   evidence: tuple[StagedLossEvidence, ...]) -> None:
        timestamp = draft.created_at.isoformat()
        self._db.execute("SAVEPOINT loss22_save_draft")
        try:
            self._db.execute(
                "INSERT INTO loss_offline_drafts "
                "(id,operation_id,device_id,branch_id,warehouse_id,actor_user_id,"
                "payload_json,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,'DRAFT',?,?)",
                (draft.draft_id, draft.operation_id, draft.device_id, draft.branch_id,
                 draft.warehouse_id, draft.actor_user_id,
                 json.dumps(draft.payload, ensure_ascii=False, sort_keys=True),
                 timestamp, timestamp),
            )
            for item in evidence:
                self._db.execute(
                    "INSERT INTO loss_offline_evidence "
                    "(id,draft_id,evidence_type,storage_uri,checksum,byte_size,created_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (item.evidence_id, draft.draft_id, item.evidence_type,
                     item.storage_uri, item.checksum, item.byte_size, timestamp),
                )
            self._db.execute("RELEASE SAVEPOINT loss22_save_draft")
        except Exception:
            self._db.execute("ROLLBACK TO SAVEPOINT loss22_save_draft")
            self._db.execute("RELEASE SAVEPOINT loss22_save_draft")
            raise

    def get_draft(self, draft_id: str) -> OfflineLossDraft | None:
        row = self._db.execute(
            "SELECT id,operation_id,device_id,branch_id,warehouse_id,actor_user_id,"
            "payload_json,created_at FROM loss_offline_drafts WHERE id=?",
            (draft_id,),
        ).fetchone()
        if row is None:
            return None
        return OfflineLossDraft(
            draft_id=str(row[0]), operation_id=str(row[1]), device_id=str(row[2]),
            branch_id=str(row[3]), warehouse_id=str(row[4]), actor_user_id=str(row[5]),
            payload=json.loads(row[6]), created_at=datetime.fromisoformat(row[7]),
        )

    def get_evidence(self, draft_id: str) -> tuple[StagedLossEvidence, ...]:
        rows = self._db.execute(
            "SELECT id,evidence_type,storage_uri,checksum,byte_size "
            "FROM loss_offline_evidence WHERE draft_id=? ORDER BY created_at,id",
            (draft_id,),
        ).fetchall()
        return tuple(StagedLossEvidence(
            evidence_id=str(row[0]), evidence_type=str(row[1]),
            storage_uri=str(row[2]), checksum=str(row[3]), byte_size=int(row[4]),
        ) for row in rows)

    def next_sequence(self, device_id: str) -> int:
        row = self._db.execute(
            "SELECT COALESCE(MAX(local_sequence),0)+1 FROM loss_sync_outbox WHERE device_id=?",
            (device_id,),
        ).fetchone()
        return int(row[0])

    def enqueue(self, envelope: LossSyncEnvelope) -> LossSyncEnvelope:
        existing = self._db.execute(
            "SELECT id,draft_id,operation_id,device_id,branch_id,local_sequence,"
            "base_revision,payload_json,payload_hash,attempt_count,last_error "
            "FROM loss_sync_outbox WHERE operation_id=?", (envelope.operation_id,),
        ).fetchone()
        if existing is not None:
            return self._envelope(existing)
        timestamp = _now()
        self._db.execute("SAVEPOINT loss22_enqueue")
        try:
            self._db.execute(
                "INSERT INTO loss_sync_outbox "
                "(id,draft_id,operation_id,device_id,branch_id,local_sequence,base_revision,"
                "payload_json,payload_hash,status,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,'PENDING',?,?)",
                (envelope.envelope_id, envelope.draft_id, envelope.operation_id,
                 envelope.device_id, envelope.branch_id, envelope.local_sequence,
                 envelope.base_revision, envelope.payload_json, envelope.payload_hash,
                 timestamp, timestamp),
            )
            self._db.execute(
                "UPDATE loss_offline_drafts SET status='QUEUED',updated_at=? WHERE id=?",
                (timestamp, envelope.draft_id),
            )
            self._db.execute("RELEASE SAVEPOINT loss22_enqueue")
        except Exception:
            self._db.execute("ROLLBACK TO SAVEPOINT loss22_enqueue")
            self._db.execute("RELEASE SAVEPOINT loss22_enqueue")
            raise
        return envelope

    def list_ready(self, limit: int):
        rows = self._db.execute(
            "SELECT id,draft_id,operation_id,device_id,branch_id,local_sequence,"
            "base_revision,payload_json,payload_hash,attempt_count,last_error "
            "FROM loss_sync_outbox WHERE status IN ('PENDING','RETRY') "
            "ORDER BY device_id,local_sequence LIMIT ?", (limit,),
        ).fetchall()
        return tuple(self._envelope(row) for row in rows)

    def mark_synced(self, envelope_id: str, remote_revision: str) -> None:
        timestamp = _now()
        self._db.execute("SAVEPOINT loss22_synced")
        try:
            row = self._required_envelope(envelope_id)
            self._db.execute(
                "UPDATE loss_sync_outbox SET status='SYNCED',last_error='',updated_at=? WHERE id=?",
                (timestamp, envelope_id),
            )
            self._db.execute(
                "UPDATE loss_offline_drafts SET status='SYNCED',remote_revision=?,updated_at=? WHERE id=?",
                (remote_revision, timestamp, row[0]),
            )
            self._db.execute(
                "UPDATE loss_offline_evidence SET upload_status='UPLOADED' WHERE draft_id=?",
                (row[0],),
            )
            self._db.execute("RELEASE SAVEPOINT loss22_synced")
        except Exception:
            self._db.execute("ROLLBACK TO SAVEPOINT loss22_synced")
            self._db.execute("RELEASE SAVEPOINT loss22_synced")
            raise

    def mark_retry(self, envelope_id: str, error: str) -> None:
        self._db.execute(
            "UPDATE loss_sync_outbox SET status='RETRY',attempt_count=attempt_count+1,"
            "last_error=?,updated_at=? WHERE id=? AND status IN ('PENDING','RETRY')",
            (error[:500], _now(), envelope_id),
        )

    def mark_conflict(self, envelope_id: str, conflict_type: str,
                      remote_revision: str,
                      remote_payload: dict[str, object]) -> None:
        timestamp = _now()
        self._db.execute("SAVEPOINT loss22_conflict")
        try:
            row = self._required_envelope(envelope_id)
            exists = self._db.execute(
                "SELECT 1 FROM loss_sync_conflicts WHERE envelope_id=?", (envelope_id,),
            ).fetchone()
            if exists is None:
                self._db.execute(
                    "INSERT INTO loss_sync_conflicts "
                    "(id,envelope_id,conflict_type,remote_revision,remote_payload_json,detected_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (new_uuid(), envelope_id, conflict_type, remote_revision,
                     json.dumps(remote_payload, ensure_ascii=False, sort_keys=True), timestamp),
                )
            self._db.execute(
                "UPDATE loss_sync_outbox SET status='CONFLICT',updated_at=? WHERE id=?",
                (timestamp, envelope_id),
            )
            self._db.execute(
                "UPDATE loss_offline_drafts SET status='CONFLICT',remote_revision=?,updated_at=? WHERE id=?",
                (remote_revision, timestamp, row[0]),
            )
            self._db.execute("RELEASE SAVEPOINT loss22_conflict")
        except Exception:
            self._db.execute("ROLLBACK TO SAVEPOINT loss22_conflict")
            self._db.execute("RELEASE SAVEPOINT loss22_conflict")
            raise

    def _required_envelope(self, envelope_id: str):
        row = self._db.execute(
            "SELECT draft_id FROM loss_sync_outbox WHERE id=?", (envelope_id,),
        ).fetchone()
        if row is None:
            raise LookupError("Loss sync envelope not found")
        return row

    @staticmethod
    def _envelope(row) -> LossSyncEnvelope:
        return LossSyncEnvelope(
            envelope_id=str(row[0]), draft_id=str(row[1]), operation_id=str(row[2]),
            device_id=str(row[3]), branch_id=str(row[4]), local_sequence=int(row[5]),
            base_revision=str(row[6]), payload_json=str(row[7]), payload_hash=str(row[8]),
            attempt_count=int(row[9]), last_error=str(row[10]),
        )

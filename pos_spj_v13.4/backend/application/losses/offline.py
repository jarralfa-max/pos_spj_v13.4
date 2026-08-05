"""Offline-first capture and synchronization contracts for Losses (LOSS-22)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from typing import Protocol, Sequence

from backend.shared.ids import new_uuid, validate_uuidv7


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


class LossSyncOutcome(str, Enum):
    ACCEPTED = "ACCEPTED"
    CONFLICT = "CONFLICT"
    RETRY = "RETRY"


@dataclass(frozen=True, slots=True)
class OfflineEvidenceInput:
    path: str
    evidence_type: str = "FILE"


@dataclass(frozen=True, slots=True)
class StagedLossEvidence:
    evidence_id: str
    evidence_type: str
    storage_uri: str
    checksum: str
    byte_size: int


@dataclass(frozen=True, slots=True)
class CreateOfflineLossDraftCommand:
    device_id: str
    branch_id: str
    warehouse_id: str
    actor_user_id: str
    payload: dict[str, object]
    evidence: tuple[OfflineEvidenceInput, ...] = ()


@dataclass(frozen=True, slots=True)
class OfflineLossDraft:
    draft_id: str
    operation_id: str
    device_id: str
    branch_id: str
    warehouse_id: str
    actor_user_id: str
    payload: dict[str, object]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class LossSyncEnvelope:
    envelope_id: str
    draft_id: str
    operation_id: str
    device_id: str
    branch_id: str
    local_sequence: int
    base_revision: str
    payload_json: str
    payload_hash: str
    attempt_count: int = 0
    last_error: str = ""

    def with_retry(self, error: str) -> "LossSyncEnvelope":
        return replace(self, attempt_count=self.attempt_count + 1, last_error=error)


@dataclass(frozen=True, slots=True)
class LossSyncAcknowledgement:
    envelope_id: str
    outcome: LossSyncOutcome
    remote_revision: str = ""
    conflict_type: str = ""
    remote_payload: dict[str, object] | None = None
    error_code: str = ""


@dataclass(frozen=True, slots=True)
class LossSyncCycleResult:
    sent: int
    synced: int
    conflicts: int
    retries: int


class LossOfflineRepository(Protocol):
    def save_draft(self, draft: OfflineLossDraft,
                   evidence: tuple[StagedLossEvidence, ...]) -> None: ...
    def get_draft(self, draft_id: str) -> OfflineLossDraft | None: ...
    def get_evidence(self, draft_id: str) -> tuple[StagedLossEvidence, ...]: ...
    def next_sequence(self, device_id: str) -> int: ...
    def enqueue(self, envelope: LossSyncEnvelope) -> LossSyncEnvelope: ...
    def list_ready(self, limit: int) -> Sequence[LossSyncEnvelope]: ...
    def mark_synced(self, envelope_id: str, remote_revision: str) -> None: ...
    def mark_retry(self, envelope_id: str, error: str) -> None: ...
    def mark_conflict(self, envelope_id: str, conflict_type: str,
                      remote_revision: str,
                      remote_payload: dict[str, object]) -> None: ...


class LossEvidenceStore(Protocol):
    def stage(self, *, source_path: Path, evidence_id: str, checksum: str) -> str: ...


class LossSyncTransport(Protocol):
    def push(self, *, device_id: str, branch_id: str,
             envelopes: Sequence[LossSyncEnvelope]) -> Sequence[LossSyncAcknowledgement]: ...


class LossOfflineDraftService:
    """Creates recoverable drafts and queues each operation exactly once."""

    def __init__(self, *, repository: LossOfflineRepository,
                 evidence_store: LossEvidenceStore) -> None:
        self._repository = repository
        self._evidence_store = evidence_store

    def create(self, command: CreateOfflineLossDraftCommand) -> OfflineLossDraft:
        for value in (command.device_id, command.branch_id, command.warehouse_id,
                      command.actor_user_id):
            validate_uuidv7(value)
        if not isinstance(command.payload, dict) or not command.payload:
            raise ValueError("Offline loss draft requires a payload")
        _canonical_json(command.payload)
        draft = OfflineLossDraft(
            draft_id=new_uuid(), operation_id=new_uuid(), device_id=command.device_id,
            branch_id=command.branch_id, warehouse_id=command.warehouse_id,
            actor_user_id=command.actor_user_id, payload=command.payload,
            created_at=_utc_now(),
        )
        evidence = tuple(self._stage_evidence(item) for item in command.evidence)
        self._repository.save_draft(draft, evidence)
        return draft

    def enqueue(self, draft_id: str, *, base_revision: str = "") -> LossSyncEnvelope:
        validate_uuidv7(draft_id)
        draft = self._repository.get_draft(draft_id)
        if draft is None:
            raise LookupError("Offline loss draft not found")
        evidence = self._repository.get_evidence(draft_id)
        payload_json = _canonical_json({
            "draft_id": draft.draft_id,
            "operation_id": draft.operation_id,
            "warehouse_id": draft.warehouse_id,
            "actor_user_id": draft.actor_user_id,
            "payload": draft.payload,
            "evidence": [
                {"evidence_id": item.evidence_id, "evidence_type": item.evidence_type,
                 "storage_uri": item.storage_uri, "checksum": item.checksum,
                 "byte_size": item.byte_size}
                for item in evidence
            ],
        })
        envelope = LossSyncEnvelope(
            envelope_id=new_uuid(), draft_id=draft.draft_id,
            operation_id=draft.operation_id, device_id=draft.device_id,
            branch_id=draft.branch_id,
            local_sequence=self._repository.next_sequence(draft.device_id),
            base_revision=str(base_revision), payload_json=payload_json,
            payload_hash=sha256(payload_json.encode("utf-8")).hexdigest(),
        )
        return self._repository.enqueue(envelope)

    def _stage_evidence(self, item: OfflineEvidenceInput) -> StagedLossEvidence:
        source = Path(item.path).expanduser().resolve(strict=True)
        if not source.is_file():
            raise ValueError("Offline evidence must be a file")
        digest = sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        evidence_id = new_uuid()
        checksum = digest.hexdigest()
        storage_uri = self._evidence_store.stage(
            source_path=source, evidence_id=evidence_id, checksum=checksum)
        return StagedLossEvidence(evidence_id, item.evidence_type.strip() or "FILE",
                                  storage_uri, checksum, source.stat().st_size)


class LossOfflineSyncService:
    """Pushes scoped envelopes; conflicts are persisted and never auto-merged."""

    def __init__(self, *, repository: LossOfflineRepository,
                 transport: LossSyncTransport, batch_size: int = 50) -> None:
        if not 1 <= batch_size <= 500:
            raise ValueError("Sync batch size must be between 1 and 500")
        self._repository = repository
        self._transport = transport
        self._batch_size = batch_size

    def synchronize(self, *, device_id: str, branch_id: str) -> LossSyncCycleResult:
        validate_uuidv7(device_id)
        validate_uuidv7(branch_id)
        ready = tuple(
            row for row in self._repository.list_ready(self._batch_size)
            if row.device_id == device_id and row.branch_id == branch_id
        )
        if not ready:
            return LossSyncCycleResult(0, 0, 0, 0)
        try:
            responses = {ack.envelope_id: ack for ack in self._transport.push(
                device_id=device_id, branch_id=branch_id, envelopes=ready)}
        except Exception:
            responses = {}
        synced = conflicts = retries = 0
        for envelope in ready:
            ack = responses.get(envelope.envelope_id)
            if ack is not None and ack.outcome is LossSyncOutcome.ACCEPTED:
                self._repository.mark_synced(envelope.envelope_id, ack.remote_revision)
                synced += 1
            elif ack is not None and ack.outcome is LossSyncOutcome.CONFLICT:
                self._repository.mark_conflict(
                    envelope.envelope_id, ack.conflict_type or "REMOTE_CONFLICT",
                    ack.remote_revision, ack.remote_payload or {})
                conflicts += 1
            else:
                error = ack.error_code if ack is not None else "TRANSPORT_UNAVAILABLE"
                self._repository.mark_retry(envelope.envelope_id, error or "SYNC_RETRY")
                retries += 1
        return LossSyncCycleResult(len(ready), synced, conflicts, retries)

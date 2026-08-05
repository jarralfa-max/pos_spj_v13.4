"""LOSS-22 behavior: drafts, evidence, outbox, sync, and conflicts."""

import unittest
from pathlib import Path

from backend.application.losses.offline import (
    CreateOfflineLossDraftCommand,
    LossOfflineDraftService,
    LossOfflineSyncService,
    LossSyncAcknowledgement,
    LossSyncOutcome,
    OfflineEvidenceInput,
)
from backend.shared.ids import is_uuidv7, new_uuid


class MemoryOfflineRepository:
    def __init__(self):
        self.drafts = {}
        self.evidence = {}
        self.outbox = {}
        self.conflicts = []

    def save_draft(self, draft, evidence):
        self.drafts[draft.draft_id] = draft
        self.evidence[draft.draft_id] = evidence

    def get_draft(self, draft_id):
        return self.drafts.get(draft_id)

    def get_evidence(self, draft_id):
        return self.evidence.get(draft_id, ())

    def enqueue(self, envelope):
        previous = next((row for row in self.outbox.values()
                         if row.operation_id == envelope.operation_id), None)
        if previous:
            return previous
        self.outbox[envelope.envelope_id] = envelope
        return envelope

    def next_sequence(self, device_id):
        values = [row.local_sequence for row in self.outbox.values()
                  if row.device_id == device_id]
        return max(values, default=0) + 1

    def list_ready(self, limit):
        return tuple(sorted(self.outbox.values(), key=lambda row: row.local_sequence))[:limit]

    def mark_synced(self, envelope_id, remote_revision):
        self.outbox.pop(envelope_id)

    def mark_retry(self, envelope_id, error):
        self.outbox[envelope_id] = self.outbox[envelope_id].with_retry(error)

    def mark_conflict(self, envelope_id, conflict_type, remote_revision, remote_payload):
        self.conflicts.append((envelope_id, conflict_type, remote_revision, remote_payload))
        self.outbox.pop(envelope_id)


class MemoryEvidenceStore:
    def __init__(self): self.calls = []
    def stage(self, *, source_path, evidence_id, checksum):
        self.calls.append((source_path, evidence_id, checksum))
        return f"loss-evidence://{evidence_id}"


class Transport:
    def __init__(self, acknowledgements): self.acknowledgements = acknowledgements
    def push(self, *, device_id, branch_id, envelopes):
        return tuple(self.acknowledgements(envelope) for envelope in envelopes)


class LossOfflineTest(unittest.TestCase):
    def setUp(self):
        self.repository = MemoryOfflineRepository()
        self.evidence_store = MemoryEvidenceStore()
        self.drafts = LossOfflineDraftService(
            repository=self.repository, evidence_store=self.evidence_store)
        self.device_id, self.branch_id = new_uuid(), new_uuid()
        self.warehouse_id, self.actor_id = new_uuid(), new_uuid()

    def _command(self, evidence=()):
        return CreateOfflineLossDraftCommand(
            device_id=self.device_id, branch_id=self.branch_id,
            warehouse_id=self.warehouse_id, actor_user_id=self.actor_id,
            payload={"notes": "Caja dañada", "lines": [{"product_id": new_uuid()}]},
            evidence=evidence,
        )

    def test_draft_and_evidence_are_staged_with_uuidv7_and_checksum(self):
        temporary_root = Path(__file__).resolve().parents[3] / ".test_tmp"
        temporary_root.mkdir(exist_ok=True)
        path = temporary_root / f"{new_uuid()}.jpg"
        path.write_bytes(b"evidencia-inmutable")
        try:
            draft = self.drafts.create(self._command((OfflineEvidenceInput(str(path)),)))
        finally:
            path.unlink(missing_ok=True)
        self.assertTrue(is_uuidv7(draft.draft_id))
        self.assertTrue(is_uuidv7(draft.operation_id))
        evidence = self.repository.evidence[draft.draft_id][0]
        self.assertTrue(is_uuidv7(evidence.evidence_id))
        self.assertEqual(len(evidence.checksum), 64)
        self.assertEqual(evidence.storage_uri, f"loss-evidence://{evidence.evidence_id}")
        envelope = self.drafts.enqueue(draft.draft_id)
        self.assertIn(evidence.storage_uri, envelope.payload_json)

    def test_queue_is_idempotent_and_sequences_per_device(self):
        first = self.drafts.create(self._command())
        second = self.drafts.create(self._command())
        first_envelope = self.drafts.enqueue(first.draft_id)
        replay = self.drafts.enqueue(first.draft_id)
        second_envelope = self.drafts.enqueue(second.draft_id)
        self.assertEqual(replay.envelope_id, first_envelope.envelope_id)
        self.assertEqual((first_envelope.local_sequence, second_envelope.local_sequence), (1, 2))
        self.assertNotEqual(first_envelope.envelope_id, first_envelope.operation_id)

    def test_sync_accepts_retries_and_materializes_conflicts_without_reexecution(self):
        accepted = self.drafts.enqueue(self.drafts.create(self._command()).draft_id)
        conflict = self.drafts.enqueue(self.drafts.create(self._command()).draft_id)
        retry = self.drafts.enqueue(self.drafts.create(self._command()).draft_id)

        def acknowledge(envelope):
            if envelope.envelope_id == accepted.envelope_id:
                return LossSyncAcknowledgement(envelope.envelope_id, LossSyncOutcome.ACCEPTED,
                                               remote_revision="7")
            if envelope.envelope_id == conflict.envelope_id:
                return LossSyncAcknowledgement(envelope.envelope_id, LossSyncOutcome.CONFLICT,
                                               conflict_type="AGGREGATE_VERSION",
                                               remote_revision="8", remote_payload={"status": "SUBMITTED"})
            return LossSyncAcknowledgement(envelope.envelope_id, LossSyncOutcome.RETRY,
                                           error_code="NETWORK_UNAVAILABLE")

        result = LossOfflineSyncService(
            repository=self.repository, transport=Transport(acknowledge)).synchronize(
                device_id=self.device_id, branch_id=self.branch_id)
        self.assertEqual((result.synced, result.conflicts, result.retries), (1, 1, 1))
        self.assertEqual(self.repository.outbox[retry.envelope_id].attempt_count, 1)
        self.assertEqual(self.repository.conflicts[0][1], "AGGREGATE_VERSION")


if __name__ == "__main__":
    unittest.main()

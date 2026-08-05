"""SQLite integration coverage for LOSS-22 born-clean persistence."""

import importlib
import sqlite3
import unittest
from pathlib import Path
import shutil

from backend.application.losses.offline import (
    CreateOfflineLossDraftCommand,
    LossOfflineDraftService,
    OfflineEvidenceInput,
)
from backend.infrastructure.persistence.loss_evidence_store import LocalLossEvidenceStore
from backend.infrastructure.persistence.loss_offline_repository import SQLiteLossOfflineRepository
from backend.shared.app_paths import AppPaths
from backend.shared.ids import is_uuidv7, new_uuid


class LossOfflinePersistenceTest(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        importlib.import_module(
            "migrations.standalone.174_losses_bounded_context_schema"
        ).run(self.connection)
        temporary_root = Path(__file__).resolve().parents[3] / ".test_tmp"
        temporary_root.mkdir(exist_ok=True)
        self.temporary = temporary_root / f"loss22-{new_uuid()}"
        self.temporary.mkdir()
        self.repository = SQLiteLossOfflineRepository(self.connection)
        self.service = LossOfflineDraftService(
            repository=self.repository,
            evidence_store=LocalLossEvidenceStore(
                AppPaths(data_dir=self.temporary)),
        )

    def tearDown(self):
        self.connection.close()
        shutil.rmtree(self.temporary, ignore_errors=True)

    def test_draft_evidence_and_idempotent_outbox_survive_roundtrip(self):
        source = self.temporary / "source.jpg"
        source.write_bytes(b"offline-photo")
        draft = self.service.create(CreateOfflineLossDraftCommand(
            device_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
            actor_user_id=new_uuid(), payload={"notes": "sin red"},
            evidence=(OfflineEvidenceInput(str(source), "PHOTO"),),
        ))
        first = self.service.enqueue(draft.draft_id)
        replay = self.service.enqueue(draft.draft_id)
        self.assertEqual(first.envelope_id, replay.envelope_id)
        self.assertTrue(is_uuidv7(first.envelope_id))
        self.assertNotEqual(first.envelope_id, first.operation_id)
        self.assertEqual(len(self.repository.get_evidence(draft.draft_id)), 1)
        status = self.connection.execute(
            "SELECT status FROM loss_offline_drafts WHERE id=?", (draft.draft_id,),
        ).fetchone()[0]
        self.assertEqual(status, "QUEUED")

    def test_conflict_is_materialized_without_overwriting_local_payload(self):
        draft = self.service.create(CreateOfflineLossDraftCommand(
            device_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
            actor_user_id=new_uuid(), payload={"notes": "local"},
        ))
        envelope = self.service.enqueue(draft.draft_id)
        self.repository.mark_conflict(
            envelope.envelope_id, "AGGREGATE_VERSION", "9", {"notes": "remote"})
        row = self.connection.execute(
            "SELECT d.payload_json,d.status,c.conflict_type,c.resolution "
            "FROM loss_offline_drafts d JOIN loss_sync_outbox o ON o.draft_id=d.id "
            "JOIN loss_sync_conflicts c ON c.envelope_id=o.id WHERE d.id=?",
            (draft.draft_id,),
        ).fetchone()
        self.assertIn("local", row[0])
        self.assertEqual(row[1:], ("CONFLICT", "AGGREGATE_VERSION", "PENDING"))


if __name__ == "__main__":
    unittest.main()

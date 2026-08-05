import importlib
import sqlite3
import unittest
from datetime import datetime, timezone

from backend.application.cash_register.offline_sync import (
    CashOfflineSyncService, SyncAcknowledgement,
)
from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.shared.ids import new_uuid


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


class Transport:
    def __init__(self, outcome="ACCEPTED"):
        self.outcome, self.batches = outcome, []
    def push(self, *, device_id, branch_id, envelopes):
        self.batches.append(list(envelopes))
        return [SyncAcknowledgement(item.envelope_id, self.outcome, "remote-1",
                                    conflict={"remote_version": 2})
                for item in envelopes]


class FailingTransport:
    def push(self, **kwargs): raise ConnectionError("offline")


class CashOfflineSyncIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module(
            "migrations.standalone.175_cash_register_bounded_context_schema"
        ).run(self.db)
        self.branch, self.actor, self.device = new_uuid(), new_uuid(), new_uuid()
        with CashRegisterUnitOfWork(self.db) as uow:
            uow.sync.register_device(device_id=self.device, branch_id=self.branch,
                                     now=NOW.isoformat(), online=True)

    def tearDown(self): self.db.close()

    def add_event(self):
        event = cash_event_payload(
            CashEvents.HARDWARE_DIAGNOSED, operation_id=new_uuid(),
            entity_id=new_uuid(), branch_id=self.branch, user_id=self.actor,
        )
        with CashRegisterUnitOfWork(self.db) as uow:
            uow.events.add(event); uow.outbox.enqueue(event)

    def test_assigns_ordered_local_sequences_and_acknowledges_outbox(self):
        self.add_event(); self.add_event()
        transport = Transport()
        result = CashOfflineSyncService(transport).synchronize(
            self.db, device_id=self.device, branch_id=self.branch, now=NOW)
        self.assertEqual((result.synced, result.retries, result.conflicts), (2, 0, 0))
        self.assertEqual([item.sequence_no for item in transport.batches[0]], [1, 2])
        self.assertEqual(self.db.execute(
            "SELECT DISTINCT status FROM cash_outbox").fetchall(), [("DISPATCHED",)])

    def test_transport_failure_schedules_retry_without_losing_event(self):
        self.add_event()
        result = CashOfflineSyncService(FailingTransport()).synchronize(
            self.db, device_id=self.device, branch_id=self.branch, now=NOW)
        self.assertEqual(result.status, "RETRYING")
        row = self.db.execute(
            "SELECT state,attempt_count,next_attempt_at FROM cash_sync_envelopes"
        ).fetchone()
        self.assertEqual(row[:2], ("RETRY", 1))
        self.assertGreater(row[2], NOW.isoformat(timespec="seconds"))

    def test_conflict_is_explicit_and_blocks_later_delivery(self):
        self.add_event()
        first = CashOfflineSyncService(Transport("CONFLICT")).synchronize(
            self.db, device_id=self.device, branch_id=self.branch, now=NOW)
        self.assertEqual(first.status, "CONFLICT")
        self.add_event()
        transport = Transport()
        blocked = CashOfflineSyncService(transport).synchronize(
            self.db, device_id=self.device, branch_id=self.branch, now=NOW)
        self.assertEqual(blocked.status, "CONFLICT")
        self.assertEqual(transport.batches, [])
        state = self.db.execute(
            "SELECT sync_status FROM cash_sync_devices WHERE id=?", (self.device,)
        ).fetchone()[0]
        self.assertEqual(state, "CONFLICT")

    def test_offline_state_does_not_call_transport(self):
        self.add_event()
        with CashRegisterUnitOfWork(self.db) as uow:
            uow.sync.set_connectivity(device_id=self.device, online=False, now=NOW.isoformat())
        transport = Transport()
        result = CashOfflineSyncService(transport).synchronize(
            self.db, device_id=self.device, branch_id=self.branch, now=NOW)
        self.assertEqual(result.status, "OFFLINE")
        self.assertEqual(transport.batches, [])

    def test_manual_retry_resolution_unblocks_ordered_delivery(self):
        self.add_event()
        CashOfflineSyncService(Transport("CONFLICT")).synchronize(
            self.db, device_id=self.device, branch_id=self.branch, now=NOW)
        envelope_id = self.db.execute(
            "SELECT id FROM cash_sync_envelopes WHERE state='CONFLICT'"
        ).fetchone()[0]
        with CashRegisterUnitOfWork(self.db) as uow:
            uow.sync.resolve_conflict(envelope_id=envelope_id,
                                      strategy="RETRY_LOCAL", now=NOW.isoformat())
        transport = Transport()
        result = CashOfflineSyncService(transport).synchronize(
            self.db, device_id=self.device, branch_id=self.branch, now=NOW)
        self.assertEqual(result.status, "IDLE")
        self.assertEqual(result.synced, 1)
        self.assertEqual(transport.batches[0][0].aggregate_version, 2)


if __name__ == "__main__": unittest.main()

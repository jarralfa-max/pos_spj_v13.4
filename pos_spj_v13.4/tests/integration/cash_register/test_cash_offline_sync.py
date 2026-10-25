"""Sincronización de Caja sobre el motor de replicación único (Slice 2).

Antes (CASH-19) estas pruebas exigían que sincronizar dejara `cash_outbox` en
DISPATCHED: justo lo que sacaba los movimientos del camino a Finanzas, cuyo
despachador sólo toma filas PENDING. Ahora exigen lo contrario.
"""

import importlib
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from backend.application.cash_register.offline_sync import (
    CashOfflineSyncService,
    CashSyncStateQueryService,
    ResolveCashSyncConflictUseCase,
    SetCashSyncConnectivityUseCase,
    ensure_cash_sync_device,
)
from backend.application.cash_register.permissions import CashPermissions
from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.shared.ids import new_uuid
from backend.shared.sync.replication_envelope import ReplicationAck

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


class Transport:
    def __init__(self, outcome="ACCEPTED"):
        self.outcome, self.batches = outcome, []

    def push(self, *, station_id, branch_id, envelopes):
        self.batches.append(list(envelopes))
        return [ReplicationAck(item.event_id, self.outcome, remote_revision="remote-1",
                               error_code="" if self.outcome == "ACCEPTED" else "VERSION",
                               conflict={"remote_version": 2})
                for item in envelopes]


class FailingTransport:
    def push(self, **kwargs):
        raise ConnectionError("offline")


class Auth:
    def __init__(self, allowed=(CashPermissions.SYNC_VIEW, CashPermissions.SYNC_MANAGE)):
        self.calls, self.allowed = [], allowed

    def require(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["permission_code"] not in self.allowed:
            raise PermissionError(kwargs)


class CashOfflineSyncIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module(
            "migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        importlib.import_module("migrations.standalone.350_replication_engine").run(self.db)
        self.branch, self.actor, self.device = new_uuid(), new_uuid(), new_uuid()
        ensure_cash_sync_device(self.db, device_id=self.device, branch_id=self.branch)

    def tearDown(self):
        self.db.close()

    def add_event(self, entity_id=None):
        event = cash_event_payload(
            CashEvents.HARDWARE_DIAGNOSED, operation_id=new_uuid(),
            entity_id=entity_id or new_uuid(), branch_id=self.branch, user_id=self.actor)
        with CashRegisterUnitOfWork(self.db) as uow:
            uow.events.add(event)
            uow.outbox.enqueue(event)
        return event

    def sync(self, transport):
        return CashOfflineSyncService(transport).synchronize(
            self.db, device_id=self.device, branch_id=self.branch, now=NOW)

    def test_ordered_sequences_and_the_finance_outbox_stays_untouched(self):
        self.add_event(); self.add_event()
        transport = Transport()
        result = self.sync(transport)
        self.assertEqual((result.synced, result.retries, result.conflicts), (2, 0, 0))
        self.assertEqual([item.sequence_no for item in transport.batches[0]], [1, 2])
        self.assertEqual(self.db.execute(
            "SELECT DISTINCT status FROM cash_outbox").fetchall(), [("PENDING",)])

    def test_transport_failure_schedules_retry_without_losing_event(self):
        self.add_event()
        result = self.sync(FailingTransport())
        self.assertEqual(result.status, "RETRYING")
        row = self.db.execute(
            "SELECT state, attempt_count, next_attempt_at FROM replication_envelopes").fetchone()
        self.assertEqual(row[:2], ("RETRY", 1))
        self.assertGreater(row[2], NOW.isoformat(timespec="seconds"))
        self.assertEqual(self.db.execute("SELECT status FROM cash_outbox").fetchone()[0],
                         "PENDING")

    def test_sync_query_service_exposes_state_and_recent_envelopes_by_scope(self):
        self.add_event()
        self.sync(FailingTransport())
        auth = Auth(allowed=(CashPermissions.SYNC_VIEW,))
        query = CashSyncStateQueryService(auth)
        state = query.get(self.db, device_id=self.device, branch_id=self.branch,
                          actor_user_id=self.actor)
        envelopes = query.list_envelopes(self.db, device_id=self.device,
                                         branch_id=self.branch, actor_user_id=self.actor)
        self.assertEqual(state["pending_count"], 1)
        self.assertEqual(state["sync_status"], "RETRYING")
        self.assertEqual(envelopes[0]["state"], "RETRY")
        self.assertEqual(envelopes[0]["attempt_count"], 1)
        self.assertEqual(envelopes[0]["event_name"], CashEvents.HARDWARE_DIAGNOSED)
        self.assertEqual(auth.calls[0]["permission_code"], CashPermissions.SYNC_VIEW)
        with self.assertRaises(LookupError):
            query.get(self.db, device_id=self.device, branch_id=new_uuid(),
                      actor_user_id=self.actor)

    def test_conflict_is_explicit_and_blocks_only_its_aggregate(self):
        caja = new_uuid()
        self.add_event(caja)
        first = self.sync(Transport("CONFLICT"))
        self.assertEqual(first.status, "CONFLICT")
        later_same = self.add_event(caja)
        other = self.add_event()
        transport = Transport()
        blocked = self.sync(transport)
        sent = [item.event_id for item in transport.batches[0]]
        self.assertEqual(sent, [other["event_id"]])
        self.assertNotIn(later_same["event_id"], sent)
        self.assertEqual(blocked.status, "CONFLICT")
        conflicts = CashSyncStateQueryService(Auth()).list_conflicts(
            self.db, device_id=self.device, branch_id=self.branch, actor_user_id=self.actor)
        self.assertEqual([c["state"] for c in conflicts], ["CONFLICT"])

    def test_offline_state_does_not_call_transport(self):
        self.add_event()
        SetCashSyncConnectivityUseCase(Auth()).execute(
            self.db, device_id=self.device, branch_id=self.branch,
            actor_user_id=self.actor, online=False)
        transport = Transport()
        result = self.sync(transport)
        self.assertEqual(result.status, "OFFLINE")
        self.assertEqual(transport.batches, [])

    def test_manual_retry_resolution_unblocks_and_leaves_a_trail(self):
        self.add_event()
        self.sync(Transport("CONFLICT"))
        envelope_id = self.db.execute(
            "SELECT id FROM replication_envelopes WHERE state='CONFLICT'").fetchone()[0]
        with self.assertRaises(ValueError):
            ResolveCashSyncConflictUseCase(Auth()).execute(
                self.db, envelope_id=envelope_id, strategy="RETRY_LOCAL", reason=" ",
                branch_id=self.branch, actor_user_id=self.actor, operation_id=new_uuid())
        ResolveCashSyncConflictUseCase(Auth()).execute(
            self.db, envelope_id=envelope_id, strategy="RETRY_LOCAL",
            reason="el servidor ya corrigió el turno", branch_id=self.branch,
            actor_user_id=self.actor, operation_id=new_uuid())
        transport = Transport()
        # La resolución reencola «desde ahora» (reloj real).
        result = CashOfflineSyncService(transport).synchronize(
            self.db, device_id=self.device, branch_id=self.branch,
            now=datetime.now(timezone.utc) + timedelta(seconds=5))
        self.assertEqual(result.status, "IDLE")
        resent = [i for i in transport.batches[0]
                  if i.event_type == CashEvents.HARDWARE_DIAGNOSED]
        # Se reenvía el MISMO sobre: misma versión y misma huella.
        self.assertEqual(resent[0].aggregate_version, 1)
        self.assertEqual(resent[0].content_hash, self.db.execute(
            "SELECT content_hash FROM replication_envelopes WHERE id=?",
            (envelope_id,)).fetchone()[0])
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM cash_domain_events WHERE event_name=?",
            (CashEvents.SYNC_CONFLICT_RESOLVED,)).fetchone()[0], 1)

    def test_accept_remote_stops_resending_and_needs_manage_permission(self):
        self.add_event()
        self.sync(Transport("CONFLICT"))
        envelope_id = self.db.execute(
            "SELECT id FROM replication_envelopes WHERE state='CONFLICT'").fetchone()[0]
        with self.assertRaises(PermissionError):
            ResolveCashSyncConflictUseCase(Auth(allowed=(CashPermissions.SYNC_VIEW,))).execute(
                self.db, envelope_id=envelope_id, strategy="ACCEPT_REMOTE", reason="x",
                branch_id=self.branch, actor_user_id=self.actor, operation_id=new_uuid())
        ResolveCashSyncConflictUseCase(Auth()).execute(
            self.db, envelope_id=envelope_id, strategy="ACCEPT_REMOTE",
            reason="prevalece el central", branch_id=self.branch,
            actor_user_id=self.actor, operation_id=new_uuid())
        self.assertEqual(self.db.execute(
            "SELECT state FROM replication_envelopes WHERE id=?", (envelope_id,)).fetchone()[0],
            "SYNCED")


if __name__ == "__main__":
    unittest.main()

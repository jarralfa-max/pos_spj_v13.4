import importlib
import sqlite3
import unittest
from datetime import datetime, timezone

from backend.application.cash_register.notifications import (
    CashInAppAlertQueryService, DispatchCashNotificationsUseCase,
    PrepareCashNotificationsUseCase,
)
from backend.application.cash_register.permissions import CashPermissions
from backend.domain.cash_register.events import CashEvents, cash_event_payload
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.shared.ids import new_uuid


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


class Sender:
    def __init__(self, fail=False): self.fail, self.messages = fail, []
    def send(self, message):
        self.messages.append(message)
        if self.fail: raise ConnectionError("provider details")
        return "provider-1"


class AllowNotificationAuth:
    def __init__(self):
        self.calls = []
    def require(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["permission_code"] != CashPermissions.NOTIFICATIONS_VIEW:
            raise AssertionError(kwargs)


class CashNotificationsIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        importlib.import_module("migrations.standalone.176_cash_register_configuration_schema").run(self.db)
        self.branch, self.user, self.rule = new_uuid(), new_uuid(), new_uuid()
        effective = "2026-01-01T00:00:00+00:00"
        self.db.execute(
            """INSERT INTO cash_alert_rules
            (id,event_name,severity,channels_json,scope_type,scope_id,active,effective_from)
            VALUES(?,?,?,'[\"IN_APP\",\"WHATSAPP\",\"EMAIL\"]','BRANCH',?,1,?)""",
            (self.rule, CashEvents.DIFFERENCE_DETECTED, "CRITICAL", self.branch, effective),
        )
        self.db.execute("INSERT INTO cash_in_app_recipients VALUES(?,?,?,?,1)",
                        (new_uuid(), self.rule, self.user, "Supervisor"))
        self.db.execute("INSERT INTO cash_whatsapp_recipients VALUES(?,?,?,?,1)",
                        (new_uuid(), self.rule, "+525512345678", "Supervisor"))
        self.db.execute("INSERT INTO cash_email_recipients VALUES(?,?,?,?,1)",
                        (new_uuid(), self.rule, "caja@example.com", "Supervisor"))
        event = cash_event_payload(
            CashEvents.DIFFERENCE_DETECTED, operation_id=new_uuid(), entity_id=new_uuid(),
            branch_id=self.branch, user_id=self.user, amount="500.00",
        )
        with CashRegisterUnitOfWork(self.db) as uow:
            uow.events.add(event); uow.outbox.enqueue(event)
        self.event_id = event["event_id"]

    def tearDown(self): self.db.close()

    def test_policy_recipients_channels_audit_and_idempotency(self):
        prepare = PrepareCashNotificationsUseCase()
        self.assertEqual(prepare.execute(self.db, event_id=self.event_id).prepared, 3)
        self.assertEqual(prepare.execute(self.db, event_id=self.event_id).prepared, 0)
        whatsapp = Sender()
        result = DispatchCashNotificationsUseCase(whatsapp=whatsapp).execute(self.db, now=NOW)
        self.assertEqual((result.delivered, result.skipped, result.retries), (2, 1, 0))
        self.assertEqual(whatsapp.messages[0].recipient, "+525512345678")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_in_app_alerts").fetchone()[0], 1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_notification_attempts").fetchone()[0], 3)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_audit_log WHERE action LIKE 'CASH_NOTIFICATION_%'").fetchone()[0], 3)

    def test_query_service_exposes_dashboard_alerts_and_queue_by_branch(self):
        PrepareCashNotificationsUseCase().execute(self.db, event_id=self.event_id)
        DispatchCashNotificationsUseCase(whatsapp=Sender()).execute(self.db, now=NOW)
        auth = AllowNotificationAuth()
        query = CashInAppAlertQueryService(auth)

        dashboard = query.dashboard(self.db, user_id=self.user, branch_id=self.branch)
        alerts = query.unread(self.db, user_id=self.user, branch_id=self.branch)
        jobs = query.recent_jobs(self.db, user_id=self.user, branch_id=self.branch)

        self.assertEqual(dashboard["unread"], 1)
        self.assertEqual(dashboard["delivered"], 2)
        self.assertEqual(len(alerts), 1)
        self.assertEqual({job["channel"] for job in jobs}, {"IN_APP", "WHATSAPP", "EMAIL"})
        self.assertEqual(auth.calls[0]["permission_code"], CashPermissions.NOTIFICATIONS_VIEW)

    def test_provider_failure_retries_without_duplicate_job_or_leaking_error(self):
        PrepareCashNotificationsUseCase().execute(self.db, event_id=self.event_id)
        result = DispatchCashNotificationsUseCase(whatsapp=Sender(fail=True)).execute(self.db, now=NOW)
        self.assertEqual(result.retries, 1)
        row = self.db.execute(
            "SELECT status,last_error,next_attempt_at FROM cash_notification_jobs WHERE channel='WHATSAPP'"
        ).fetchone()
        self.assertEqual(row[0:2], ("RETRY", "PROVIDER_UNAVAILABLE"))
        self.assertNotIn("provider details", " ".join(str(value) for value in row))
        self.assertGreater(row[2], NOW.isoformat(timespec="seconds"))

    def test_branch_policy_overrides_system_policy(self):
        system_rule = new_uuid()
        self.db.execute(
            """INSERT INTO cash_alert_rules
            (id,event_name,severity,channels_json,scope_type,scope_id,active,effective_from)
            VALUES(?,?,?,'[\"EMAIL\"]','SYSTEM',NULL,1,?)""",
            (system_rule, CashEvents.DIFFERENCE_DETECTED, "WARNING", "2025-01-01T00:00:00+00:00"),
        )
        policy = CashRegisterUnitOfWork(self.db).notifications.resolve_policy(
            event_name=CashEvents.DIFFERENCE_DETECTED, branch_id=self.branch,
            occurred_at=NOW.isoformat(),
        )
        self.assertEqual(policy["id"], self.rule)


if __name__ == "__main__": unittest.main()

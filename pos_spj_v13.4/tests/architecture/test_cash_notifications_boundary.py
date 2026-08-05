import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CashNotificationsBoundaryTest(unittest.TestCase):
    def test_application_uses_sender_ports_not_provider_sdks(self):
        source = (ROOT / "backend/application/cash_register/notifications.py").read_text(encoding="utf-8")
        self.assertIn("class CashNotificationSender(Protocol)", source)
        for forbidden in ("twilio", "sendgrid", "smtp", "requests.post"):
            self.assertNotIn(forbidden, source.lower())

    def test_notification_schema_is_migration_owned(self):
        migration = (ROOT / "migrations/standalone/176_cash_register_configuration_schema.py").read_text(encoding="utf-8")
        self.assertIn("cash_notification_jobs", migration)
        self.assertIn("cash_notification_attempts", migration)
        self.assertIn("cash_in_app_alerts", migration)

    def test_idempotency_constraint_is_event_channel_recipient(self):
        migration = (ROOT / "migrations/standalone/176_cash_register_configuration_schema.py").read_text(encoding="utf-8")
        self.assertIn("UNIQUE(source_event_id,channel,recipient)", migration)


if __name__ == "__main__": unittest.main()

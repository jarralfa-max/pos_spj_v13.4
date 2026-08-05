import unittest

from backend.application.cash_register.notifications import CashNotificationMessage
from backend.infrastructure.integrations.cash_notification_senders import (
    EmailNotificationSender, WhatsAppNotificationSender,
)


class Client:
    def __init__(self): self.calls = []
    def send_text(self, **kwargs): self.calls.append(kwargs); return "wa-1"
    def send_email(self, **kwargs): self.calls.append(kwargs); return "mail-1"


class CashNotificationSendersTest(unittest.TestCase):
    def test_whatsapp_uses_e164_and_job_as_provider_idempotency_key(self):
        client = Client()
        reference = WhatsAppNotificationSender(client).send(
            CashNotificationMessage("job-uuid", "+525512345678", "CRITICAL", "Alerta", "Detalle"))
        self.assertEqual(reference, "wa-1")
        self.assertEqual(client.calls[0]["idempotency_key"], "job-uuid")

    def test_whatsapp_rejects_non_e164_recipient(self):
        with self.assertRaises(ValueError):
            WhatsAppNotificationSender(Client()).send(
                CashNotificationMessage("job", "5512345678", "INFO", "A", "B"))

    def test_email_adapter_is_optional_and_idempotent_at_provider(self):
        client = Client()
        EmailNotificationSender(client).send(
            CashNotificationMessage("job-uuid", "caja@example.com", "INFO", "A", "B"))
        self.assertEqual(client.calls[0]["idempotency_key"], "job-uuid")


if __name__ == "__main__": unittest.main()

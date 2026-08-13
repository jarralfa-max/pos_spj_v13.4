import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CashNotificationsUiWiringTest(unittest.TestCase):
    def test_notifications_route_uses_view_permission_and_capability(self):
        routes = (ROOT / "frontend/desktop/modules/cash_register/cash_register_routes.py").read_text(encoding="utf-8")
        self.assertIn('"notifications"', routes)
        self.assertIn("CashPermissions.NOTIFICATIONS_VIEW", routes)
        self.assertIn('"notification_view"', routes)

    def test_notifications_page_has_no_sql_or_direct_provider_calls(self):
        page = (ROOT / "frontend/desktop/modules/cash_register/cash_notifications_page.py").read_text(encoding="utf-8")
        forbidden = (
            "SELECT ", "INSERT ", "UPDATE ", "DELETE ",
            "cash_in_app_alerts", "send_text", "send_email", "WhatsAppNotificationSender",
            "EmailNotificationSender", "sqlite3",
        )
        for token in forbidden:
            self.assertNotIn(token, page)
        self.assertIn("dispatch_cash_notifications", page)
        self.assertIn("cash_notification_jobs", page)

    def test_factory_owns_whatsapp_adapter_and_presenter_exposes_dispatch(self):
        factory = (ROOT / "backend/infrastructure/desktop/cash_register_factory.py").read_text(encoding="utf-8")
        presenter = (ROOT / "frontend/desktop/modules/cash_register/cash_register_presenter.py").read_text(encoding="utf-8")
        self.assertIn("WhatsAppNotificationSender", factory)
        self.assertIn("DispatchCashNotificationsUseCase", factory)
        self.assertIn("CashPermissions.NOTIFICATIONS_MANAGE", factory)
        self.assertIn("dispatch_cash_notifications", presenter)


if __name__ == "__main__":
    unittest.main()

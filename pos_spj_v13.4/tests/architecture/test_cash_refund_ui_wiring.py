from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CashRefundUiWiringArchitectureTests(unittest.TestCase):
    def test_refund_page_is_real_and_uses_presenter_command(self):
        page = (
            ROOT / "frontend/desktop/modules/cash_register/cash_refunds_page.py"
        ).read_text(encoding="utf-8")
        workspace = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_workspace.py"
        ).read_text(encoding="utf-8")
        dialogs = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_dialogs.py"
        ).read_text(encoding="utf-8")
        self.assertIn("class CashRefundsPage", page)
        self.assertIn("execute_cash_refund(", page)
        self.assertIn("CashRefundDialog", page)
        self.assertIn("CashRefundsPage(presenter=", workspace)
        self.assertIn("class CashRefundDialog", dialogs)
        self.assertIn("original_payment_lines", dialogs)
        self.assertIn("refund_lines", dialogs)

    def test_refund_factory_uses_cash_refund_integration_service(self):
        factory = (
            ROOT / "backend/infrastructure/desktop/cash_register_factory.py"
        ).read_text(encoding="utf-8")
        presenter = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_presenter.py"
        ).read_text(encoding="utf-8")
        self.assertIn("CashRefundIntegrationService", factory)
        self.assertIn('"execute_cash_refund"', factory)
        self.assertIn("operation_id = new_uuid()", factory)
        self.assertIn("prepare_notifications_for_operation(operation_id)", factory)
        self.assertIn("def execute_cash_refund", presenter)


if __name__ == "__main__":
    unittest.main()

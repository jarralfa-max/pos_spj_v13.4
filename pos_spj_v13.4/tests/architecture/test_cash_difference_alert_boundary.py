from pathlib import Path
import unittest


ROOT = Path(__file__).parents[2]


class CashDifferenceAlertBoundaryTests(unittest.TestCase):
    def test_whatsapp_is_requested_by_event_not_sent_directly(self):
        source = (ROOT / "backend/application/cash_register/z_cut_use_cases.py").read_text(encoding="utf-8")
        self.assertIn("whatsapp_required", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("send_whatsapp", source)
        self.assertNotIn("Twilio", source)

    def test_recurrence_is_scoped_by_branch_and_responsible_user(self):
        source = (ROOT / "backend/infrastructure/db/repositories/cash_register/repositories.py").read_text(encoding="utf-8")
        block = source[source.index("def recurrence_count"):source.index("def transition", source.index("def recurrence_count"))]
        self.assertIn("branch_id", block)
        self.assertIn("responsible_user_id", block)


if __name__ == "__main__": unittest.main()

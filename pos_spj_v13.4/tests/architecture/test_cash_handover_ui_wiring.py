from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CashHandoverUiWiringArchitectureTests(unittest.TestCase):
    def test_handover_page_is_real_and_wired_to_presenter(self):
        page = (
            ROOT / "frontend/desktop/modules/cash_register/cash_handovers_page.py"
        ).read_text(encoding="utf-8")
        workspace = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_workspace.py"
        ).read_text(encoding="utf-8")
        self.assertIn("class CashHandoversPage", page)
        self.assertIn("deliver_cash_handover(", page)
        self.assertIn("receive_cash_handover(", page)
        self.assertIn("dispute_cash_handover(", page)
        self.assertIn("CashDenominationDialog", page)
        self.assertIn("CashTextReasonDialog", page)
        self.assertIn("CashHandoversPage(query_service", workspace)

    def test_handover_factory_uses_canonical_use_cases(self):
        factory = (
            ROOT / "backend/infrastructure/desktop/cash_register_factory.py"
        ).read_text(encoding="utf-8")
        self.assertIn("CashHandoverQueryService", factory)
        self.assertIn("DeliverTreasuryHandoverUseCase", factory)
        self.assertIn("ReceiveTreasuryHandoverUseCase", factory)
        self.assertIn("DisputeTreasuryHandoverUseCase", factory)
        self.assertIn('"deliver_cash_handover"', factory)
        self.assertIn('"receive_cash_handover"', factory)
        self.assertIn('"dispute_cash_handover"', factory)


if __name__ == "__main__":
    unittest.main()

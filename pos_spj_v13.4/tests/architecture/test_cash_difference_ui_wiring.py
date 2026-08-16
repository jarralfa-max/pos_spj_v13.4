from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CashDifferenceUiWiringArchitectureTests(unittest.TestCase):
    def test_difference_page_is_real_and_wired_to_presenter(self):
        page = (
            ROOT / "frontend/desktop/modules/cash_register/cash_differences_page.py"
        ).read_text(encoding="utf-8")
        workspace = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_workspace.py"
        ).read_text(encoding="utf-8")
        self.assertIn("class CashDifferencesPage", page)
        self.assertIn("explain_cash_difference(", page)
        self.assertIn("review_cash_difference(", page)
        self.assertIn("resolve_cash_difference(", page)
        self.assertIn("ExplainCashDifferenceDialog", page)
        self.assertIn("ResolveCashDifferenceDialog", page)
        self.assertIn("CashDifferencesPage(query_service", workspace)

    def test_difference_factory_uses_canonical_use_cases(self):
        factory = (
            ROOT / "backend/infrastructure/desktop/cash_register_factory.py"
        ).read_text(encoding="utf-8")
        presenter = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_presenter.py"
        ).read_text(encoding="utf-8")
        self.assertIn("CashDifferenceQueryService", factory)
        self.assertIn("ExplainCashDifferenceUseCase", factory)
        self.assertIn("ReviewCashDifferenceUseCase", factory)
        self.assertIn("ResolveCashDifferenceUseCase", factory)
        self.assertIn('"explain_cash_difference"', factory)
        self.assertIn('"review_cash_difference"', factory)
        self.assertIn('"resolve_cash_difference"', factory)
        self.assertIn("def explain_cash_difference", presenter)


if __name__ == "__main__":
    unittest.main()

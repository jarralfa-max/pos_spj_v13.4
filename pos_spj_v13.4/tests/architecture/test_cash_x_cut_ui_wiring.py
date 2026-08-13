from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CashXCutUiWiringArchitectureTests(unittest.TestCase):
    def test_x_cut_page_is_real_and_wired_to_presenter(self):
        page = (
            ROOT / "frontend/desktop/modules/cash_register/cash_x_cuts_page.py"
        ).read_text(encoding="utf-8")
        workspace = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_workspace.py"
        ).read_text(encoding="utf-8")
        self.assertIn("class CashXCutsPage", page)
        self.assertIn("generate_x_cut(", page)
        self.assertIn("print_x_cut(", page)
        self.assertIn("CashTextReasonDialog", page)
        self.assertIn("CashXCutsPage(query_service", workspace)

    def test_x_cut_factory_uses_canonical_use_case_query_and_print_queue(self):
        factory = (
            ROOT / "backend/infrastructure/desktop/cash_register_factory.py"
        ).read_text(encoding="utf-8")
        presenter = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_presenter.py"
        ).read_text(encoding="utf-8")
        self.assertIn("XCutQueryService", factory)
        self.assertIn("GenerateXCutUseCase", factory)
        self.assertIn("PrintCashDocumentUseCase", factory)
        self.assertIn("CashPrintRepository", factory)
        self.assertIn('"generate_x_cut"', factory)
        self.assertIn('"print_x_cut"', factory)
        self.assertIn("def generate_x_cut", presenter)
        self.assertIn("def print_x_cut", presenter)


if __name__ == "__main__":
    unittest.main()

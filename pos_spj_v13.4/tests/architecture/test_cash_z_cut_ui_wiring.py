from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CashZCutUiWiringArchitectureTests(unittest.TestCase):
    def test_z_cut_page_is_real_and_wired_to_presenter(self):
        page = (
            ROOT / "frontend/desktop/modules/cash_register/cash_z_cuts_page.py"
        ).read_text(encoding="utf-8")
        workspace = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_workspace.py"
        ).read_text(encoding="utf-8")
        self.assertIn("class CashZCutsPage", page)
        self.assertIn("generate_z_cut(", page)
        self.assertIn("print_z_cut(", page)
        self.assertIn("notify_z_cut(", page)
        self.assertIn("ReprintCashDocumentDialog", page)
        self.assertIn("CashZCutsPage(query_service", workspace)

    def test_z_cut_factory_uses_canonical_use_cases_and_born_clean_print_queue(self):
        factory = (
            ROOT / "backend/infrastructure/desktop/cash_register_factory.py"
        ).read_text(encoding="utf-8")
        presenter = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_presenter.py"
        ).read_text(encoding="utf-8")
        self.assertIn("CashZCutQueryService", factory)
        self.assertIn("GenerateZCutUseCase", factory)
        self.assertIn("PrintCashDocumentUseCase", factory)
        self.assertIn("CashPrintRepository", factory)
        self.assertIn('"generate_z_cut"', factory)
        self.assertIn('"print_z_cut"', factory)
        self.assertIn('"notify_z_cut"', factory)
        self.assertIn("def generate_z_cut", presenter)
        self.assertIn("def print_z_cut", presenter)


if __name__ == "__main__":
    unittest.main()

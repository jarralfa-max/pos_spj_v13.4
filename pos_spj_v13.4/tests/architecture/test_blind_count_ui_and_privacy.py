from pathlib import Path
import unittest


ROOT = Path(__file__).parents[2]


class BlindCountUiAndPrivacyTests(unittest.TestCase):
    def test_ui_uses_canonical_components_and_has_no_sql(self):
        source = (ROOT / "frontend/desktop/modules/cash_register/blind_count_page.py").read_text(encoding="utf-8")
        for component in ("PageHeader", "KPIBar", "StandardTable", "QuantityInput"):
            self.assertIn(component, source)
        for forbidden in ("SELECT ", "sqlite3", ".commit(", ".rollback("):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("pyqtSignal", source)

    def test_ui_actions_are_wired_to_presenter_use_cases(self):
        page = (ROOT / "frontend/desktop/modules/cash_register/blind_count_page.py").read_text(encoding="utf-8")
        workspace = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_workspace.py"
        ).read_text(encoding="utf-8")
        presenter = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_presenter.py"
        ).read_text(encoding="utf-8")
        factory = (
            ROOT / "backend/infrastructure/desktop/cash_register_factory.py"
        ).read_text(encoding="utf-8")
        self.assertIn("start_blind_count(", page)
        self.assertIn("capture_blind_count_denomination(", page)
        self.assertIn("confirm_blind_count(", page)
        self.assertIn("BlindCountPage(query_service, presenter=self._presenter", workspace)
        self.assertIn("def start_blind_count", presenter)
        self.assertIn("StartBlindCountUseCase", factory)
        self.assertIn("CaptureBlindCountDenominationUseCase", factory)
        self.assertIn("ConfirmBlindCountUseCase", factory)

    def test_expected_is_revealed_only_by_query_service_permission(self):
        source = (ROOT / "backend/application/cash_register/blind_count_query_service.py").read_text(encoding="utf-8")
        self.assertIn("BLIND_COUNT_REVEAL_EXPECTED", source)
        self.assertIn('count["status"] != "CONFIRMED"', source)
        self.assertNotIn("expected_cash:", (
            ROOT / "backend/application/cash_register/blind_count_use_cases.py"
        ).read_text(encoding="utf-8"))


if __name__ == "__main__": unittest.main()

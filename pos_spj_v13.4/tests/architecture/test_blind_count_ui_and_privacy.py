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

    def test_expected_is_revealed_only_by_query_service_permission(self):
        source = (ROOT / "backend/application/cash_register/blind_count_query_service.py").read_text(encoding="utf-8")
        self.assertIn("BLIND_COUNT_REVEAL_EXPECTED", source)
        self.assertIn('count["status"] != "CONFIRMED"', source)
        self.assertNotIn("expected_cash:", (
            ROOT / "backend/application/cash_register/blind_count_use_cases.py"
        ).read_text(encoding="utf-8"))


if __name__ == "__main__": unittest.main()

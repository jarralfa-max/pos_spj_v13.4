from pathlib import Path
import unittest


ROOT = Path(__file__).parents[2]


class CashLedgerArchitectureTests(unittest.TestCase):
    def test_commands_do_not_depend_on_legacy_cash_or_finance(self):
        source = (ROOT / "backend/application/cash_register/ledger_use_cases.py").read_text(encoding="utf-8")
        self.assertNotIn("legacy", source.lower())
        self.assertNotIn("FinanceService", source)
        self.assertNotIn("UPDATE cash_ledger", source)

    def test_ui_is_thin_and_uses_canonical_components(self):
        source = (ROOT / "frontend/desktop/modules/cash_register/cash_ledger_page.py").read_text(encoding="utf-8")
        for component in ("PageHeader", "KPIBar", "StandardTable"):
            self.assertIn(component, source)
        self.assertNotIn("SELECT ", source)
        self.assertNotIn("sqlite", source)


if __name__ == "__main__": unittest.main()

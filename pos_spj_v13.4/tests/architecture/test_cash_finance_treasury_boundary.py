import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CashFinanceTreasuryBoundaryTest(unittest.TestCase):
    def test_cash_application_never_imports_finance_or_writes_finance_tables(self):
        forbidden = ("backend.domain.finance", "repositories.finance", "journal_entries",
                     "treasury_accounts", "finance_processed_events")
        for path in (ROOT / "backend/application/cash_register").glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for token in forbidden:
                self.assertNotIn(token, source, path)

    def test_finance_consumers_never_write_cash_tables(self):
        for name in ("cash_treasury_handlers.py", "cash_finance_router.py",
                     "cash_shift_closed_handler.py"):
            source = (ROOT / "backend/application/event_handlers/finance" / name).read_text(encoding="utf-8")
            self.assertNotIn("repositories.cash_register", source)
            self.assertNotIn("INSERT INTO cash_", source)
            self.assertNotIn("UPDATE cash_", source)

    def test_each_economic_effect_has_one_owner(self):
        handlers = (ROOT / "backend/application/event_handlers/finance/cash_treasury_handlers.py").read_text(encoding="utf-8")
        self.assertIn("Sales owns revenue/tax reversal", handlers)
        self.assertIn("Z-cut posting already includes over/short", handlers)
        self.assertIn("Cash prepares a deposit package only", handlers)
        self.assertIn("PostingPurpose.CASH_DEPOSIT", handlers)


if __name__ == "__main__": unittest.main()

from pathlib import Path
import unittest


ROOT = Path(__file__).parents[2]


class CashHandoverTreasuryBoundaryTests(unittest.TestCase):
    def test_treasury_transfer_is_requested_only_after_matching_reception(self):
        source = (ROOT / "backend/application/cash_register/movement_use_cases.py").read_text(encoding="utf-8")
        self.assertIn("treasury_transfer_required=matches", source)
        self.assertNotIn("treasury_transfers", source)
        self.assertNotIn("FinanceService", source)

    def test_delivery_and_reception_are_distinct_confirmations(self):
        migration = (ROOT / "migrations/standalone/175_cash_register_bounded_context_schema.py").read_text(encoding="utf-8")
        self.assertIn("cash_handover_confirmations", migration)
        self.assertIn("'DELIVERY','RECEPTION','DISPUTE'", migration)


if __name__ == "__main__": unittest.main()

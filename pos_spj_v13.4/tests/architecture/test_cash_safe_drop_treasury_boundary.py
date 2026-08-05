from pathlib import Path
import unittest


ROOT = Path(__file__).parents[2]


class CashSafeDropTreasuryBoundaryTests(unittest.TestCase):
    def test_cash_does_not_write_treasury_tables_or_import_finance(self):
        source = (ROOT / "backend/application/cash_register/movement_use_cases.py").read_text(encoding="utf-8")
        self.assertNotIn("backend.domain.finance", source)
        self.assertNotIn("treasury_accounts", source)
        self.assertNotIn("treasury_transfers", source)

    def test_handover_is_custody_not_second_ledger_outflow(self):
        source = (ROOT / "backend/application/cash_register/movement_use_cases.py").read_text(encoding="utf-8")
        prepare = source[source.index("class PrepareTreasuryHandoverUseCase"):]
        self.assertNotIn("CashMovementType.HANDOVER", prepare)


if __name__ == "__main__": unittest.main()

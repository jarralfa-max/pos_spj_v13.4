from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[2]


class CashShiftUseCaseArchitectureTests(unittest.TestCase):
    def test_shift_lifecycle_does_not_delegate_to_legacy_or_use_float(self):
        source = (REPO / "backend/application/cash_register/shift_use_cases.py").read_text(encoding="utf-8")
        for forbidden in ("FinanceService", "finance_service", "turnos_caja",
                          "movimientos_caja", "float(", "lastrowid"):
            self.assertNotIn(forbidden, source)
        for required in ("CashRegisterUnitOfWork", "CashLedgerEntry",
                         "CashAuthorizationPolicy", "CashMonetaryLimitPolicy"):
            self.assertIn(required, source)


if __name__ == "__main__": unittest.main()


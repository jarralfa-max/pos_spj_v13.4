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

    def test_shift_transition_commands_use_lifecycle_policy_not_status_strings(self):
        source = (REPO / "backend/application/cash_register/shift_use_cases.py").read_text(encoding="utf-8")
        self.assertIn("CashShiftLifecyclePolicy.ensure_transition", source)
        self.assertIn("CashShiftStatus.SUSPENDED", source)
        self.assertIn("CashShiftStatus.OPEN", source)
        self.assertIn("CashShiftStatus.CLOSING", source)
        for forbidden in (
            'source_status',
            'target_status = "OPEN"',
            'target_status = "SUSPENDED"',
            'target_status = "CLOSING"',
            'source_status, target_status',
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__": unittest.main()


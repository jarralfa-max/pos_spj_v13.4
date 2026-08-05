from pathlib import Path
import unittest


ROOT = Path(__file__).parents[2]


class ZCutAtomicBoundaryTests(unittest.TestCase):
    def test_finalization_uses_one_cash_uow_and_ports_for_outputs(self):
        source = (ROOT / "backend/application/cash_register/z_cut_use_cases.py").read_text(encoding="utf-8")
        self.assertIn("CashRegisterUnitOfWork", source)
        self.assertIn("class ZCutPrintGateway(Protocol)", source)
        self.assertIn("class ZCutNotificationGateway(Protocol)", source)
        self.assertNotIn("FinanceService", source)
        self.assertNotIn("QPrinter", source)

    def test_final_z_cut_closes_only_after_pending_validation(self):
        source = (ROOT / "backend/application/cash_register/z_cut_use_cases.py").read_text(encoding="utf-8")
        self.assertLess(source.index("unresolved_safe_drop_count"), source.index("uow.shifts.close"))
        self.assertLess(source.index("find_confirmed_for_final_cut"), source.index("uow.shifts.close"))


if __name__ == "__main__": unittest.main()

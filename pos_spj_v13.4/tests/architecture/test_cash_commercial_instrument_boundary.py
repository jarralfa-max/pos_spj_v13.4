from pathlib import Path
import unittest


ROOT = Path(__file__).parents[2]


class CashCommercialInstrumentBoundaryTests(unittest.TestCase):
    def test_cash_classifies_but_does_not_own_instrument_balances(self):
        source = (ROOT / "backend/application/cash_register/sales_integration.py").read_text(encoding="utf-8")
        for forbidden in ("loyalty_balance", "coupon_balance", "voucher_balance",
                          "store_credit_balance", "commercial_obligations"):
            self.assertNotIn(forbidden, source)

    def test_commercial_instruments_are_never_drawer_affecting(self):
        source = (ROOT / "backend/domain/cash_register/settlements.py").read_text(encoding="utf-8")
        for instrument in ("LOYALTY_POINTS", "COUPON", "VOUCHER", "STORE_CREDIT"):
            line = next(item for item in source.splitlines() if f'"{instrument}"' in item and "Definition" in item)
            self.assertIn("False", line)


if __name__ == "__main__": unittest.main()

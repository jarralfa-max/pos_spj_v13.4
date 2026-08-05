from pathlib import Path
import unittest


ROOT = Path(__file__).parents[2]


class CashRefundDomainBoundaryTests(unittest.TestCase):
    def test_cash_does_not_mutate_finance_loyalty_or_sales(self):
        source = (ROOT / "backend/application/cash_register/refund_integration.py").read_text(encoding="utf-8")
        for forbidden in ("backend.domain.finance", "loyalty_balance", "UPDATE ventas",
                          "journal_entries", "commercial_obligations"):
            self.assertNotIn(forbidden, source)
        self.assertIn('finance_event="SALE_REFUNDED"', source)
        self.assertIn("loyalty_reversal_required", source)

    def test_refund_is_not_the_cancellation_handler(self):
        source = (ROOT / "backend/application/event_handlers/cash_register/sales_cash_handlers.py").read_text(encoding="utf-8")
        self.assertIn("class SaleRefundedCashHandler", source)
        self.assertNotIn("SaleRefundedCashHandler = SaleCancelledCashHandler", source)


if __name__ == "__main__": unittest.main()

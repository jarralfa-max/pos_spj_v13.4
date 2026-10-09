from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CashRefundUiWiringArchitectureTests(unittest.TestCase):
    """CASH-26 (2026-10-07): la página de Reembolsos LISTA lo ejecutado; la
    ejecución vive en la devolución del POS (no hay segunda vía en Caja)."""

    def test_refund_page_lists_refunds_through_the_presenter(self):
        page = (
            ROOT / "frontend/desktop/modules/cash_register/cash_refunds_page.py"
        ).read_text(encoding="utf-8")
        workspace = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_workspace.py"
        ).read_text(encoding="utf-8")
        dialogs = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_dialogs.py"
        ).read_text(encoding="utf-8")
        self.assertIn("class CashRefundsPage", page)
        self.assertIn("cash_refunds(", page)
        self.assertIn("CashRefundsPage(presenter=", workspace)
        self.assertNotIn("CashRefundDialog", page + dialogs)

    def test_refunds_are_executed_only_by_the_pos_return(self):
        factory = (
            ROOT / "backend/infrastructure/desktop/cash_register_factory.py"
        ).read_text(encoding="utf-8")
        presenter = (
            ROOT / "frontend/desktop/modules/cash_register/cash_register_presenter.py"
        ).read_text(encoding="utf-8")
        pos = (
            ROOT / "frontend/desktop/modules/sales_pos/composition.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn('"execute_cash_refund"', factory)
        self.assertNotIn("def execute_cash_refund", presenter)
        self.assertIn("CashRefundIntegrationService", pos)


if __name__ == "__main__":
    unittest.main()

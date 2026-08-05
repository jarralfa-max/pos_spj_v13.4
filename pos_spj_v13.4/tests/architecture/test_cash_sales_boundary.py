from pathlib import Path
import unittest


ROOT = Path(__file__).parents[2]


class CashSalesBoundaryTests(unittest.TestCase):
    def test_integration_does_not_import_sales_legacy_or_write_sales_tables(self):
        source = (ROOT / "backend/application/cash_register/sales_integration.py").read_text(encoding="utf-8")
        self.assertNotIn("core.services.sales", source)
        self.assertNotIn("modulos.ventas", source)
        for sql in ("INSERT INTO ventas", "UPDATE ventas", "DELETE FROM ventas"):
            self.assertNotIn(sql, source)


if __name__ == "__main__": unittest.main()

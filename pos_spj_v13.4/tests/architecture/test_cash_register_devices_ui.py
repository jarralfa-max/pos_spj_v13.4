from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[2]


class CashDevicesUiTests(unittest.TestCase):
    def test_device_ui_uses_design_system_and_no_hardware_or_database(self):
        source = (REPO / "frontend/desktop/modules/cash_register/cash_devices_page.py").read_text(encoding="utf-8")
        for required in ("PageHeader", "StandardTable", "create_primary_button", "Cajas", "Cajones", "Terminales"):
            self.assertIn(required, source)
        upper = source.upper()
        for forbidden in ("SQLITE3", "SELECT ", "INSERT ", ".COMMIT(", ".ROLLBACK(",
                          "OPEN_CASH_DRAWER", "ESCPOS", "SETSTYLESHEET"):
            self.assertNotIn(forbidden, upper)


if __name__ == "__main__": unittest.main()

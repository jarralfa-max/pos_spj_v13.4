from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[2]


class CashDevicesUiTests(unittest.TestCase):
    def test_device_ui_uses_design_system_and_no_hardware_or_database(self):
        source = (REPO / "frontend/desktop/modules/cash_register/cash_devices_page.py").read_text(encoding="utf-8")
        for required in (
            "PageHeader", "StandardTable", "create_primary_button",
            "Cajas", "Cajones", "Terminales", "Diagnosticar", "Abrir cajon",
            "Mantenimiento", "Retirar",
        ):
            self.assertIn(required, source)
        upper = source.upper()
        for forbidden in ("SQLITE3", "SELECT ", "INSERT ", ".COMMIT(", ".ROLLBACK(",
                          "OPEN_DRAWER(", "ESCPOS", "SETSTYLESHEET"):
            self.assertNotIn(forbidden, upper)
        self.assertNotIn("pyqtSignal", source)

    def test_device_ui_is_wired_to_presenter_not_orphan_signals(self):
        page = (REPO / "frontend/desktop/modules/cash_register/cash_devices_page.py").read_text(encoding="utf-8")
        workspace = (
            REPO / "frontend/desktop/modules/cash_register/cash_register_workspace.py"
        ).read_text(encoding="utf-8")
        presenter = (
            REPO / "frontend/desktop/modules/cash_register/cash_register_presenter.py"
        ).read_text(encoding="utf-8")
        factory = (
            REPO / "backend/infrastructure/desktop/cash_register_factory.py"
        ).read_text(encoding="utf-8")
        self.assertIn("create_cash_device(", page)
        self.assertIn("set_cash_device_status(", page)
        self.assertIn('target_status="MAINTENANCE"', page)
        self.assertIn('target_status="RETIRED"', page)
        self.assertIn("diagnose_cash_hardware(", page)
        self.assertIn("open_cash_drawer_hardware(", page)
        self.assertIn("CashDevicesPage(query_service, presenter=self._presenter", workspace)
        self.assertIn("def diagnose_cash_hardware", presenter)
        self.assertIn("DiagnoseCashHardwareUseCase", factory)
        self.assertIn("OpenCashDrawerUseCase", factory)


if __name__ == "__main__": unittest.main()

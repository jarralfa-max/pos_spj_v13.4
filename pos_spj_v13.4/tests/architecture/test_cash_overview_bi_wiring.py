import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CashOverviewBiWiringTest(unittest.TestCase):
    def test_overview_page_is_real_and_uses_design_system(self):
        page = (ROOT / "frontend/desktop/modules/cash_register/cash_overview_page.py").read_text(encoding="utf-8")
        for required in ("PageHeader", "KPIBar", "DashboardGrid", "StandardTable", "ViewState"):
            self.assertIn(required, page)
        for forbidden in ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", "sqlite3", ".commit(", ".rollback("):
            self.assertNotIn(forbidden, page)

    def test_overview_query_service_owns_bi_calculations(self):
        service = (ROOT / "backend/application/cash_register/overview_query_service.py").read_text(encoding="utf-8")
        self.assertIn("CashOverviewQueryService", service)
        self.assertIn("Turnos activos", service)
        self.assertIn("Efectivo esperado", service)
        self.assertIn("Diferencias pendientes", service)
        self.assertIn("CashPermissions.ACCESS", service)

    def test_factory_workspace_and_presenter_mount_overview(self):
        factory = (ROOT / "backend/infrastructure/desktop/cash_register_factory.py").read_text(encoding="utf-8")
        workspace = (ROOT / "frontend/desktop/modules/cash_register/cash_register_workspace.py").read_text(encoding="utf-8")
        presenter = (ROOT / "frontend/desktop/modules/cash_register/cash_register_presenter.py").read_text(encoding="utf-8")
        self.assertIn("CashOverviewQueryService", factory)
        self.assertIn('"overview"', factory)
        self.assertIn("CashOverviewPage", workspace)
        self.assertIn("cash_overview_dashboard", presenter)


if __name__ == "__main__":
    unittest.main()

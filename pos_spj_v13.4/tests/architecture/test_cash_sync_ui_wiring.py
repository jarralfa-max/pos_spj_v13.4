import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CashSyncUiWiringTest(unittest.TestCase):
    def test_sync_route_uses_view_permission_and_capability(self):
        routes = (ROOT / "frontend/desktop/modules/cash_register/cash_register_routes.py").read_text(encoding="utf-8")
        self.assertIn('"sync"', routes)
        self.assertIn("CashPermissions.SYNC_VIEW", routes)
        self.assertIn('"sync_view"', routes)
        self.assertNotIn("CashPermissions.SYNC_MANAGE,\n        \"sync_view\"", routes)

    def test_sync_page_has_no_sql_repository_or_transport_dependency(self):
        page = (ROOT / "frontend/desktop/modules/cash_register/cash_sync_page.py").read_text(encoding="utf-8")
        forbidden = ("SELECT ", "INSERT ", "UPDATE ", "DELETE ",
                     "CashSyncRepository", "CashSyncTransport", "sqlite3")
        for token in forbidden:
            self.assertNotIn(token, page)
        self.assertIn("run_cash_sync_cycle", page)
        self.assertIn("resolve_cash_sync_conflict", page)
        self.assertIn("set_cash_sync_connectivity", page)

    def test_workspace_mounts_sync_page_instead_of_placeholder(self):
        workspace = (ROOT / "frontend/desktop/modules/cash_register/cash_register_workspace.py").read_text(encoding="utf-8")
        self.assertIn("CashSyncPage", workspace)
        self.assertIn('if key == "sync"', workspace)


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "frontend/desktop/modules/cash_register"


class CashRegisterUiUxWorkspaceTests(unittest.TestCase):
    def test_workspace_covers_navigation_states_responsive_and_accessibility(self):
        source = (MODULE / "cash_register_workspace.py").read_text(encoding="utf-8")
        for required in (
            "SideNav",
            "QStackedWidget",
            "PageHeader",
            "KPIBar",
            "ViewState",
            "create_state_widget",
            "ResponsiveBreakpoints",
            "setAccessibleName",
            "setAccessibleDescription",
            "apply_tooltip",
            "resizeEvent",
        ):
            self.assertIn(required, source)
        upper = source.upper()
        for forbidden in ("SQLITE3", "SELECT ", "INSERT ", "UPDATE ", "DELETE ",
                          ".COMMIT(", ".ROLLBACK(", "SETSTYLESHEET"):
            self.assertNotIn(forbidden, upper)

    def test_routes_cover_cash_23_pages_in_spanish(self):
        source = (MODULE / "cash_register_routes.py").read_text(encoding="utf-8")
        for label in (
            "Resumen",
            "Apertura y turnos",
            "Ledger",
            "Conteo ciego",
            "Corte X",
            "Corte Z",
            "Diferencias",
            "Entrega de valores",
            "Reembolsos",
            "Hardware",
            "Configuracion",
        ):
            self.assertIn(label, source)
        self.assertIn("cash_register.configuration.view", source)

    def test_dialogs_use_standard_components_and_audit_fields(self):
        source = (MODULE / "cash_register_dialogs.py").read_text(encoding="utf-8")
        for required in (
            "FormDialog",
            "StandardDialog",
            "MoneyInput",
            "StandardLineEdit",
            "StandardTextArea",
            "PasswordInput",
            "apply_tooltip",
            "HotAuthorizationResult",
        ):
            self.assertIn(required, source)
        upper = source.upper()
        for forbidden in ("QMESSAGEBOX", "SETSTYLESHEET", "SQLITE3", ".COMMIT(", ".ROLLBACK("):
            self.assertNotIn(forbidden, upper)

    def test_juanis_side_nav_theme_is_global_qss(self):
        qss = (ROOT / "frontend/desktop/themes/qss_builder.py").read_text(encoding="utf-8")
        self.assertIn("QListWidget#sideNav", qss)
        self.assertIn("PRIMARY_SUBTLE", qss)
        self.assertIn("PRIMARY_DEFAULT", qss)


if __name__ == "__main__":
    unittest.main()

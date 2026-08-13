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
            "Depositos preparados",
            "Reembolsos",
            "Medios de pago",
            "Terminales de pago",
            "Eventos de cajon",
            "Hardware",
            "Auditoria",
            "Configuracion",
        ):
            self.assertIn(label, source)
        self.assertIn("CashPermissions.SETTINGS_VIEW", source)
        self.assertIn("CashPermissions.PAYMENT_METHOD_VIEW", source)
        self.assertIn("CashPermissions.PAYMENT_TERMINAL_VIEW", source)
        self.assertIn("CashPermissions.DRAWER_EVENT_VIEW", source)
        self.assertIn("CashPermissions.AUDIT_VIEW", source)
        self.assertNotIn("cash_register.configuration.view", source)

    def test_secondary_pages_are_backend_backed_not_placeholders(self):
        workspace = (MODULE / "cash_register_workspace.py").read_text(encoding="utf-8")
        presenter = (MODULE / "cash_register_presenter.py").read_text(encoding="utf-8")
        page = (MODULE / "cash_operational_read_page.py").read_text(encoding="utf-8")
        factory = (ROOT / "backend/infrastructure/desktop/cash_register_factory.py").read_text(
            encoding="utf-8"
        )
        for route in ("deposits", "payment_methods", "payment_terminals", "drawer_events", "audit"):
            self.assertIn(route, workspace)
            self.assertIn(route, presenter)
        self.assertIn("CashOperationalReadPage", workspace)
        self.assertIn("cash_operational_section", presenter)
        self.assertIn('"operational_read"', factory)
        self.assertIn("CashOperationalReadQueryService", factory)
        upper = page.upper()
        for forbidden in ("SQLITE3", "SELECT ", "INSERT ", "UPDATE ", "DELETE ",
                          ".COMMIT(", ".ROLLBACK(", "REPOSITORY"):
            self.assertNotIn(forbidden, upper)

    def test_routes_use_canonical_caja_permissions_without_legacy_translation(self):
        routes = (MODULE / "cash_register_routes.py").read_text(encoding="utf-8")
        permissions = (ROOT / "backend/application/cash_register/permissions.py").read_text(encoding="utf-8")
        presenter = (MODULE / "cash_register_presenter.py").read_text(encoding="utf-8")
        for source in (routes, permissions, presenter):
            self.assertNotIn('"cash_register.', source)
            self.assertNotIn("'cash_register.", source)
            self.assertNotIn("CASH_ACCESS", source)
        self.assertIn('ACCESS = "CAJA.ver"', permissions)
        self.assertIn("SessionContext.tiene_permiso", permissions)
        self.assertIn("CashPermissions.ACCESS", routes)

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

    def test_configuration_page_is_wired_to_presenter_and_use_case(self):
        page = (MODULE / "cash_configuration_page.py").read_text(encoding="utf-8")
        workspace = (MODULE / "cash_register_workspace.py").read_text(encoding="utf-8")
        presenter = (MODULE / "cash_register_presenter.py").read_text(encoding="utf-8")
        factory = (ROOT / "backend/infrastructure/desktop/cash_register_factory.py").read_text(
            encoding="utf-8"
        )
        use_case = (ROOT / "backend/application/cash_register/configuration_use_cases.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("CashConfigurationDialog", page)
        self.assertIn("configure_cash_register(", page)
        self.assertNotIn("pyqtSignal", page)
        self.assertIn("presenter=self._presenter", workspace)
        self.assertIn("def configure_cash_register", presenter)
        self.assertIn("ConfigureCashRegisterUseCase", factory)
        self.assertIn("CashRegisterUnitOfWork", use_case)
        self.assertIn("CashPermissions.SETTINGS_MANAGE", use_case)

    def test_juanis_side_nav_theme_is_global_qss(self):
        qss = (ROOT / "frontend/desktop/themes/qss_builder.py").read_text(encoding="utf-8")
        self.assertIn("QListWidget#sideNav", qss)
        self.assertIn("PRIMARY_SUBTLE", qss)
        self.assertIn("PRIMARY_DEFAULT", qss)


if __name__ == "__main__":
    unittest.main()

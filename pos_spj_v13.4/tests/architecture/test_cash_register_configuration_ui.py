from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[2]
PAGE = REPO / "frontend/desktop/modules/cash_register/cash_configuration_page.py"


class CashConfigurationUiTests(unittest.TestCase):
    def test_ui_is_thin_spanish_and_uses_standard_components(self):
        source = PAGE.read_text(encoding="utf-8")
        for component in ("PageHeader", "StandardTable", "create_primary_button"):
            self.assertIn(component, source)
        for label in ("Jerarquía", "Vigencias", "Denominaciones", "Medios de pago",
                      "Límites", "Alertas", "WhatsApp", "Permisos"):
            self.assertIn(label, source)
        upper = source.upper()
        for forbidden in ("SQLITE3", "SELECT ", "INSERT ", "UPDATE ", "DELETE ",
                          ".COMMIT(", ".ROLLBACK(", "SETSTYLESHEET"):
            self.assertNotIn(forbidden, upper)


if __name__ == "__main__":
    unittest.main()

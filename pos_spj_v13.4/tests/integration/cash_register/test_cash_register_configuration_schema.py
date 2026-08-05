import importlib
import sqlite3
import unittest


class CashConfigurationSchemaTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.176_cash_register_configuration_schema").run(self.db)

    def tearDown(self): self.db.close()

    def test_configuration_tables_and_indexes_are_born_clean(self):
        tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        expected = {"cash_settings", "cash_denominations", "cash_payment_methods",
                    "cash_operation_limits", "cash_alert_rules", "cash_whatsapp_recipients",
                    "cash_permission_profiles", "cash_permission_profile_items"}
        self.assertTrue(expected <= tables)
        sql = "\n".join(row[0] or "" for row in self.db.execute("SELECT sql FROM sqlite_master"))
        self.assertNotIn("AUTOINCREMENT", sql.upper())
        self.assertNotIn(" REAL", sql.upper())
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_bootstrap_is_idempotent_and_seeds_no_business_defaults(self):
        importlib.import_module("migrations.standalone.176_cash_register_configuration_schema").run(self.db)
        for table in ("cash_denominations", "cash_payment_methods", "cash_operation_limits", "cash_alert_rules"):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)


if __name__ == "__main__": unittest.main()


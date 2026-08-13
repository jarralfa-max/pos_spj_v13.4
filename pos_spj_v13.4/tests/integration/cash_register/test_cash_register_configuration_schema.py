import importlib
import sqlite3
import unittest

from backend.application.cash_register.configuration_use_cases import ConfigureCashRegisterUseCase
from backend.application.cash_register.permissions import CashPermissions
from backend.shared.ids import new_uuid


class AllowSettingsAuth:
    def __init__(self):
        self.calls = []

    def require(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["permission_code"] != CashPermissions.SETTINGS_MANAGE:
            raise AssertionError(kwargs)


class CashConfigurationSchemaTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
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

    def test_configuration_use_case_writes_catalog_audit_event_and_outbox_atomically(self):
        auth = AllowSettingsAuth()
        branch_id, actor_id = new_uuid(), new_uuid()
        result = ConfigureCashRegisterUseCase(auth).execute(
            self.db,
            section="limits",
            name="SAFE_DROP",
            value="100.00 / 500.00",
            scope_type="SYSTEM",
            scope_id=None,
            actor_user_id=actor_id,
            branch_id=branch_id,
            operation_id=new_uuid(),
            effective_from="2026-08-01T00:00:00+00:00",
        )
        self.assertTrue(result.entity_id)
        self.assertEqual(
            self.db.execute("SELECT approval_threshold,hard_cap FROM cash_operation_limits").fetchone(),
            ("100.00", "500.00"),
        )
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_audit_log").fetchone()[0], 1)
        self.assertEqual(
            self.db.execute("SELECT event_name FROM cash_domain_events").fetchone()[0],
            "CASH_CONFIGURATION_CHANGED",
        )
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_outbox").fetchone()[0], 1)
        self.assertEqual(auth.calls[0]["permission_code"], CashPermissions.SETTINGS_MANAGE)


if __name__ == "__main__": unittest.main()


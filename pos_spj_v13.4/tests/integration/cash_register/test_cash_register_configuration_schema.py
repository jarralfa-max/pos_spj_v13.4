import importlib
import sqlite3
import unittest
from decimal import Decimal

from backend.application.cash_register.permissions import CashPermissions
from backend.application.cash_register.configuration_use_cases import (
    CashConfigurationScope,
    ConfigureCashAlertRuleCommand,
    ConfigureCashDenominationCommand,
    ConfigureCashOperationLimitCommand,
    ConfigureCashPaymentMethodCommand,
    ConfigureCashRegisterUseCase,
)
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
                    "cash_permission_profiles", "cash_permission_profile_items",
                    "cash_movement_reasons", "cash_difference_policies",
                    "cash_in_app_recipients", "cash_email_recipients",
                    "cash_notification_jobs", "cash_notification_attempts",
                    "cash_in_app_alerts"}
        self.assertTrue(expected <= tables)
        sql = "\n".join(row[0] or "" for row in self.db.execute("SELECT sql FROM sqlite_master"))
        self.assertNotIn("AUTOINCREMENT", sql.upper())
        self.assertNotIn(" REAL", sql.upper())
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_permission_profiles_accept_only_caja_action_codes(self):
        profile_id = new_uuid()
        self.db.execute(
            "INSERT INTO cash_permission_profiles(id,name,description,active,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?)",
            (profile_id, "cajero", "Perfil operativo", 1, "now", "now"),
        )
        self.db.execute(
            "INSERT INTO cash_permission_profile_items(id,profile_id,permission_code) VALUES(?,?,?)",
            (new_uuid(), profile_id, CashPermissions.SHIFT_OPEN),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "INSERT INTO cash_permission_profile_items(id,profile_id,permission_code) VALUES(?,?,?)",
                (new_uuid(), profile_id, "CASH_SHIFT_OPEN"),
            )

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

    def test_typed_configuration_commands_write_enterprise_catalogs(self):
        auth = AllowSettingsAuth()
        branch_id, actor_id = new_uuid(), new_uuid()
        use_case = ConfigureCashRegisterUseCase(auth)
        use_case.execute_typed(
            self.db,
            command=ConfigureCashDenominationCommand(
                currency_code="MXN",
                value=Decimal("200.00"),
                display_name="$200",
                sort_order=2,
            ),
            actor_user_id=actor_id,
            branch_id=branch_id,
            operation_id=new_uuid(),
        )
        use_case.execute_typed(
            self.db,
            command=ConfigureCashPaymentMethodCommand(
                code="BANK_CARD",
                display_name="Tarjeta bancaria",
                affects_physical_cash=False,
            ),
            actor_user_id=actor_id,
            branch_id=branch_id,
            operation_id=new_uuid(),
        )
        use_case.execute_typed(
            self.db,
            command=ConfigureCashAlertRuleCommand(
                event_name="CASH_Z_CUT_GENERATED",
                severity="CRITICAL",
                channels=("IN_APP", "WHATSAPP"),
                scope=CashConfigurationScope.from_values("BRANCH", branch_id),
            ),
            actor_user_id=actor_id,
            branch_id=branch_id,
            operation_id=new_uuid(),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT currency_code,denomination_value,display_name,sort_order FROM cash_denominations"
            ).fetchone(),
            ("MXN", "200.00", "$200", 2),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT code,display_name,affects_physical_cash FROM cash_payment_methods"
            ).fetchone(),
            ("BANK_CARD", "Tarjeta bancaria", 0),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT event_name,severity,channels_json,scope_type,scope_id FROM cash_alert_rules"
            ).fetchone(),
            ("CASH_Z_CUT_GENERATED", "CRITICAL", '["IN_APP", "WHATSAPP"]', "BRANCH", branch_id),
        )
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_outbox").fetchone()[0], 3)

    def test_typed_configuration_rejects_invalid_limit_before_persistence(self):
        auth = AllowSettingsAuth()
        branch_id, actor_id = new_uuid(), new_uuid()
        with self.assertRaises(ValueError):
            ConfigureCashRegisterUseCase(auth).execute_typed(
                self.db,
                command=ConfigureCashOperationLimitCommand(
                    operation_type="SAFE_DROP",
                    approval_threshold=Decimal("500.00"),
                    hard_cap=Decimal("100.00"),
                    scope=CashConfigurationScope.from_values("SYSTEM"),
                ),
                actor_user_id=actor_id,
                branch_id=branch_id,
                operation_id=new_uuid(),
            )
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM cash_operation_limits").fetchone()[0], 0)

    def test_legacy_payload_wrapper_delegates_to_typed_configuration(self):
        auth = AllowSettingsAuth()
        branch_id, actor_id = new_uuid(), new_uuid()
        ConfigureCashRegisterUseCase(auth).execute(
            self.db,
            section="payment_methods",
            name="CASH",
            value="Efectivo",
            scope_type="SYSTEM",
            scope_id=None,
            actor_user_id=actor_id,
            branch_id=branch_id,
            operation_id=new_uuid(),
            effective_from="2026-08-01T00:00:00+00:00",
        )
        self.assertEqual(
            self.db.execute(
                "SELECT code,display_name,affects_physical_cash,effective_from FROM cash_payment_methods"
            ).fetchone(),
            ("CASH", "Efectivo", 1, "2026-08-01T00:00:00+00:00"),
        )


if __name__ == "__main__": unittest.main()


import importlib
import sqlite3
import unittest

from backend.application.cash_register.operational_read_query_service import (
    CashOperationalReadQueryService,
)
from backend.application.cash_register.permissions import CashPermissions
from backend.shared.ids import new_uuid


class AllowExactAuth:
    def __init__(self):
        self.calls = []

    def require(self, **kwargs):
        self.calls.append(kwargs)


class CashOperationalReadQueryServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.176_cash_register_configuration_schema").run(self.db)
        importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema").run(self.db)
        self.branch = new_uuid()
        self.user = new_uuid()
        self.register = new_uuid()
        self.terminal = new_uuid()
        now = "2026-08-01T10:00:00+00:00"
        self.db.execute(
            "INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
            (self.register, self.branch, "Caja 1", "ACTIVE", None, now, now),
        )
        self.db.execute(
            "INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
            (self.terminal, self.branch, self.register, "Terminal 1", "ACTIVE", now, now),
        )
        self.db.execute(
            """INSERT INTO cash_payment_methods
            (id,code,display_name,affects_physical_cash,active,effective_from)
            VALUES(?,?,?,?,?,?)""",
            (new_uuid(), "CASH", "Efectivo", 1, 1, now),
        )
        self.db.execute(
            """INSERT INTO cash_domain_events
            (id,event_name,operation_id,entity_id,branch_id,user_id,occurred_at,payload_json)
            VALUES(?,?,?,?,?,?,?,?)""",
            (
                new_uuid(),
                "CASH_DRAWER_OPENED",
                new_uuid(),
                new_uuid(),
                self.branch,
                self.user,
                now,
                '{"reason":"NO_SALE_AUTHORIZED"}',
            ),
        )
        self.db.execute(
            """INSERT INTO cash_domain_events
            (id,event_name,operation_id,entity_id,branch_id,user_id,occurred_at,payload_json)
            VALUES(?,?,?,?,?,?,?,?)""",
            (
                new_uuid(),
                "CASH_DEPOSIT_PREPARED",
                new_uuid(),
                new_uuid(),
                self.branch,
                self.user,
                now,
                '{"amount":"100.00","currency_code":"MXN"}',
            ),
        )
        self.db.execute(
            """INSERT INTO cash_audit_log
            (id,action,actor_user_id,entity_id,branch_id,operation_id,reason,occurred_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            (new_uuid(), "CASH_DRAWER_OPENED", self.user, new_uuid(),
             self.branch, new_uuid(), "Auditoria operativa", now),
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_sections_return_rows_and_require_exact_view_permissions(self):
        auth = AllowExactAuth()
        service = CashOperationalReadQueryService(self.db, auth)

        expected_permissions = {
            "deposits": CashPermissions.DEPOSIT_VIEW,
            "payment_methods": CashPermissions.PAYMENT_METHOD_VIEW,
            "payment_terminals": CashPermissions.PAYMENT_TERMINAL_VIEW,
            "drawer_events": CashPermissions.DRAWER_EVENT_VIEW,
            "audit": CashPermissions.AUDIT_VIEW,
        }
        for section_key, permission in expected_permissions.items():
            with self.subTest(section_key=section_key):
                section = service.section(
                    section_key=section_key,
                    branch_id=self.branch,
                    requester_user_id=self.user,
                )
                self.assertEqual(section.key, section_key)
                self.assertEqual(len(section.rows), 1)
                self.assertEqual(auth.calls[-1]["permission_code"], permission)
                if section_key != "payment_methods":
                    self.assertEqual(auth.calls[-1]["branch_id"], self.branch)


if __name__ == "__main__":
    unittest.main()
